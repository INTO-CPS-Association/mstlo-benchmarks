mod latency;
#[cfg(feature = "ros")]
mod ros;
mod simulation;

use std::{
    cell::{Cell, RefCell},
    collections::BTreeMap,
    path::PathBuf,
    rc::Rc,
    time::{Duration, Instant},
};

use clap::{Args, Parser, Subcommand, ValueEnum};
use futures::{StreamExt, future::LocalBoxFuture, stream};
use latency::LatencyTracker;
use mstlo::{Algorithm, Semantics, SynchronizationStrategy};
use smol::LocalExecutor;
use trustworthiness_checker::{
    InputBatch, InputEvent, InputStream, OutputStream, Runtime, VarName,
    core::OutputHandler,
    lang::mstlo::parse_named_properties,
    runtime::{
        RuntimeBuilder,
        mstlo::{MstloRuntimeBuilder, MstloTimedValue, MstloValue},
    },
};

use simulation::{Position, Simulation};

#[global_allocator]
static GLOBAL: tikv_jemallocator::Jemalloc = tikv_jemallocator::Jemalloc;

#[derive(Parser)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    Direct(CommonArgs),
    #[cfg(feature = "ros")]
    Ros {
        #[command(flatten)]
        common: CommonArgs,
        #[arg(long)]
        output_map: PathBuf,
        #[arg(long, default_value = "")]
        topic_namespace: String,
        #[arg(long, default_value_t = 2.0)]
        discovery_s: f64,
        #[arg(long, default_value_t = 2.0)]
        drain_s: f64,
    },
}

#[derive(Clone, Copy, PartialEq, Eq, ValueEnum)]
enum SemanticsArg {
    DelayedQualitative,
    DelayedQuantitative,
    EagerQualitative,
    RobustnessInterval,
}

impl SemanticsArg {
    fn latency_baseline_ms(self, finalization_horizon_ms: u64) -> u64 {
        match self {
            Self::EagerQualitative | Self::RobustnessInterval => 0,
            Self::DelayedQualitative | Self::DelayedQuantitative => finalization_horizon_ms,
        }
    }

    fn accepts(self, value: MstloValue) -> bool {
        match (self, value) {
            (Self::DelayedQuantitative, MstloValue::Float(_)) => true,
            (Self::DelayedQualitative | Self::EagerQualitative, MstloValue::Bool(_)) => true,
            (Self::RobustnessInterval, MstloValue::RobustnessInterval(lower, upper)) => {
                !lower.is_nan() && !upper.is_nan() && lower <= upper
            }
            _ => false,
        }
    }

    #[cfg(feature = "ros")]
    fn accepts_ros(self, value: &r2r::robo_sapiens_interfaces::msg::MstloTimedValue) -> bool {
        match self {
            Self::DelayedQuantitative => value.kind == 0,
            Self::DelayedQualitative | Self::EagerQualitative => value.kind == 1,
            Self::RobustnessInterval => {
                value.kind == 2
                    && !value.interval_lower.is_nan()
                    && !value.interval_upper.is_nan()
                    && value.interval_lower <= value.interval_upper
            }
        }
    }
}

impl From<SemanticsArg> for Semantics {
    fn from(value: SemanticsArg) -> Self {
        match value {
            SemanticsArg::DelayedQualitative => Self::DelayedQualitative,
            SemanticsArg::DelayedQuantitative => Self::DelayedQuantitative,
            SemanticsArg::EagerQualitative => Self::EagerQualitative,
            SemanticsArg::RobustnessInterval => Self::RobustnessInterval,
        }
    }
}

#[derive(Args)]
pub struct CommonArgs {
    #[arg(long)]
    properties: PathBuf,
    #[arg(long)]
    robots: usize,
    #[arg(long)]
    seed: u64,
    #[arg(long)]
    duration_s: f64,
    #[arg(long)]
    publish_rate_hz: f64,
    #[arg(long, default_value_t = 60.0)]
    sim_hz: f64,
    #[arg(long)]
    horizon_ms: u64,
    #[arg(long, value_enum)]
    semantics: SemanticsArg,
}

fn main() -> anyhow::Result<()> {
    match Cli::parse().command {
        Command::Direct(args) => run_direct(&args),
        #[cfg(feature = "ros")]
        Command::Ros {
            common,
            output_map,
            topic_namespace,
            discovery_s,
            drain_s,
        } => ros::run(&common, &output_map, &topic_namespace, discovery_s, drain_s),
    }
}

struct LatencyOutput {
    streams: Option<BTreeMap<VarName, OutputStream<MstloTimedValue>>>,
    tracker: Rc<RefCell<LatencyTracker>>,
    semantics: SemanticsArg,
    invalid_outputs: Rc<Cell<u64>>,
}

impl OutputHandler for LatencyOutput {
    type Val = MstloTimedValue;

    fn provide_streams(&mut self, streams: BTreeMap<VarName, OutputStream<Self::Val>>) {
        self.streams = Some(streams);
    }

    fn run(&mut self) -> LocalBoxFuture<'static, anyhow::Result<()>> {
        let tracker = self.tracker.clone();
        let semantics = self.semantics;
        let invalid_outputs = self.invalid_outputs.clone();
        let streams: Vec<_> = self
            .streams
            .take()
            .unwrap_or_default()
            .into_iter()
            .filter_map(|(name, stream)| {
                let property_id = tracker.borrow().property_id(&name)?;
                Some(stream.map(move |output| (property_id, output)))
            })
            .collect();
        Box::pin(async move {
            let mut outputs = stream::select_all(streams);
            while let Some((property_id, output)) = outputs.next().await {
                if !semantics.accepts(output.value) {
                    invalid_outputs.set(invalid_outputs.get().saturating_add(1));
                    continue;
                }
                if let Ok(timestamp) = output.timestamp.as_nanos().try_into() {
                    tracker.borrow_mut().record_output(property_id, timestamp);
                }
            }
            Ok(())
        })
    }
}

struct Source {
    simulation: Simulation,
    tracker: Rc<RefCell<LatencyTracker>>,
    positions: Vec<Position>,
    signal_names: Vec<(VarName, VarName)>,
    robot: usize,
    y_axis: bool,
    timestamp: Duration,
    index: usize,
    samples: usize,
    rate: f64,
    started: Option<Instant>,
}

fn run_direct(args: &CommonArgs) -> anyhow::Result<()> {
    anyhow::ensure!(args.robots > 0, "direct input requires at least one robot");
    let properties = std::fs::read_to_string(&args.properties)?;
    let model = parse_named_properties(&properties)?;
    let tracker = Rc::new(RefCell::new(LatencyTracker::new(
        args.horizon_ms,
        args.semantics.latency_baseline_ms(args.horizon_ms),
        model.formulae().keys().cloned(),
    )));
    let source = Source {
        simulation: Simulation::new(args.robots, args.seed, args.sim_hz, args.publish_rate_hz),
        tracker: tracker.clone(),
        positions: Vec::with_capacity(args.robots),
        signal_names: (0..args.robots)
            .map(|robot| {
                (
                    VarName::new(&format!("robot_{robot}_x")),
                    VarName::new(&format!("robot_{robot}_y")),
                )
            })
            .collect(),
        robot: 0,
        y_axis: false,
        timestamp: Duration::ZERO,
        index: 0,
        samples: (args.duration_s * args.publish_rate_hz).ceil() as usize,
        rate: args.publish_rate_hz,
        started: None,
    };
    let input: InputStream<MstloTimedValue> =
        Box::pin(stream::unfold(source, |mut source| async move {
            if source.robot >= source.positions.len() {
                if source.index >= source.samples {
                    return None;
                }
                source.timestamp = Duration::from_secs_f64(source.index as f64 / source.rate);
                let started = *source.started.get_or_insert_with(Instant::now);
                smol::Timer::at(started + source.timestamp).await;
                source.positions.clear();
                source
                    .positions
                    .extend_from_slice(source.simulation.next_sample());
                let timestamp_ns = source.timestamp.as_nanos().try_into().unwrap_or(u64::MAX);
                source.tracker.borrow_mut().record_input(timestamp_ns);
                source.robot = 0;
                source.y_axis = false;
                source.index += 1;
            }

            let robot = source.robot;
            let position = source.positions[robot];
            let (name, value) = if source.y_axis {
                source.robot += 1;
                source.y_axis = false;
                (source.signal_names[robot].1.clone(), position.y)
            } else {
                source.y_axis = true;
                (source.signal_names[robot].0.clone(), position.x)
            };
            let event = InputEvent::new(
                name,
                MstloTimedValue::new(source.timestamp, MstloValue::Float(value)),
            );
            Some((Ok(InputBatch::events(vec![event])), source))
        }));

    let executor = Rc::new(LocalExecutor::new());
    let runtime_executor = executor.clone();
    let output_tracker = tracker.clone();
    let invalid_outputs = Rc::new(Cell::new(0_u64));
    let runtime_invalid_outputs = invalid_outputs.clone();
    smol::block_on(executor.run(async move {
        let runtime = MstloRuntimeBuilder::<MstloTimedValue>::new()
            .executor(runtime_executor)
            .model(model)
            .algorithm(Algorithm::Incremental)
            .semantics(args.semantics.into())
            .synchronization_strategy(SynchronizationStrategy::ZeroOrderHold)
            .input(input)
            .output(Box::new(LatencyOutput {
                streams: None,
                tracker: output_tracker,
                semantics: args.semantics,
                invalid_outputs: runtime_invalid_outputs,
            }))
            .build()
            .await;
        runtime.run().await
    }))?;
    let summary = tracker.borrow_mut().summary(invalid_outputs.get());
    anyhow::ensure!(
        summary.latency_invalid_outputs == 0,
        "direct runtime emitted {} invalid outputs",
        summary.latency_invalid_outputs
    );
    anyhow::ensure!(
        summary.latency_complete,
        "direct runtime produced {} of {} expected property/timestamp verdicts",
        summary.latency_samples,
        summary.latency_expected_samples
    );
    println!("{}", serde_json::to_string(&summary)?);
    Ok(())
}
