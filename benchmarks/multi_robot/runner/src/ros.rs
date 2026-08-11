use std::{
    collections::BTreeMap,
    path::Path,
    pin::Pin,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
        mpsc,
    },
    thread,
    time::{Duration, Instant},
};

use futures::{FutureExt, Stream, StreamExt, stream};
use r2r::{
    Context, Node, Publisher, builtin_interfaces::msg::Duration as RosDuration, qos::QosProfile,
    robo_sapiens_interfaces::msg::MstloTimedValue,
};
use serde::Deserialize;
use trustworthiness_checker::VarName;

use crate::{CommonArgs, SemanticsArg, latency::LatencyTracker, simulation::Simulation};

const FLOAT_KIND: u8 = 0;
const INPUT_DEPTH: usize = 64;
const OUTPUT_DEPTH: usize = 256;
/// Percentage of expected property/timestamp verdicts a ROS run must collect.
/// Transport under load drops a small tail, so the run is accepted and reported
/// as incomplete rather than failed.
const MIN_VERDICT_PERCENT: u64 = 90;

struct Publishers {
    x: Publisher<MstloTimedValue>,
    y: Publisher<MstloTimedValue>,
}

#[derive(Deserialize)]
struct TopicMapping {
    topic: String,
}

type VerdictStream = Pin<Box<dyn Stream<Item = (usize, MstloTimedValue)>>>;

pub fn run(
    args: &CommonArgs,
    output_map: &Path,
    topic_namespace: &str,
    discovery_s: f64,
    drain_s: f64,
) -> anyhow::Result<()> {
    anyhow::ensure!(args.robots > 0, "ROS input requires at least one robot");
    let mappings: BTreeMap<String, TopicMapping> =
        serde_json::from_str(&std::fs::read_to_string(output_map)?)?;
    anyhow::ensure!(!mappings.is_empty(), "ROS output map is empty");

    let property_names: Vec<_> = mappings.keys().map(|name| VarName::new(name)).collect();
    let tracker = Arc::new(Mutex::new(LatencyTracker::new(
        args.horizon_ms,
        args.semantics.latency_baseline_ms(args.horizon_ms),
        property_names,
    )));
    let stop_collector = Arc::new(AtomicBool::new(false));
    let collector = start_collector(
        mappings,
        tracker.clone(),
        args.semantics,
        stop_collector.clone(),
    )?;

    let context = Context::create()?;
    let mut node = Node::create(context, "mstlo_benchmark_source", "")?;
    let mut publishers = Vec::with_capacity(args.robots);
    for robot in 0..args.robots {
        publishers.push(Publishers {
            x: node.create_publisher(&input_topic(topic_namespace, robot, "x"), input_qos())?,
            y: node.create_publisher(&input_topic(topic_namespace, robot, "y"), input_qos())?,
        });
    }

    spin_until(
        &mut node,
        Instant::now() + Duration::from_secs_f64(discovery_s),
    );

    let mut simulation = Simulation::new(args.robots, args.seed, args.sim_hz, args.publish_rate_hz);
    let samples = (args.duration_s * args.publish_rate_hz).ceil() as usize;
    let period = Duration::from_secs_f64(1.0 / args.publish_rate_hz);
    let started = Instant::now();

    for index in 0..samples {
        spin_until(&mut node, started + period.mul_f64(index as f64));
        let source_time = Duration::from_secs_f64(index as f64 / args.publish_rate_hz);
        let ros_time = RosDuration {
            sec: i32::try_from(source_time.as_secs())?,
            nanosec: source_time.subsec_nanos(),
        };
        let positions = simulation.next_sample();
        tracker
            .lock()
            .expect("latency tracker lock poisoned")
            .record_input(source_time.as_nanos().try_into()?);
        for (position, output) in positions.iter().zip(&publishers) {
            output.x.publish(&message(ros_time.clone(), position.x))?;
            output.y.publish(&message(ros_time.clone(), position.y))?;
        }
        node.spin_once(Duration::ZERO);
    }

    spin_until(&mut node, Instant::now() + Duration::from_secs_f64(drain_s));
    stop_collector.store(true, Ordering::Release);
    let invalid_outputs = collector
        .join()
        .map_err(|_| anyhow::anyhow!("ROS verdict collector panicked"))??;

    let summary = tracker
        .lock()
        .expect("latency tracker lock poisoned")
        .summary(invalid_outputs);
    anyhow::ensure!(
        summary.latency_invalid_outputs == 0,
        "ROS emitted {} invalid outputs",
        summary.latency_invalid_outputs
    );
    anyhow::ensure!(
        summary.meets_completeness(MIN_VERDICT_PERCENT),
        "ROS produced {} of {} expected property/timestamp verdicts, below the {}% minimum",
        summary.latency_samples,
        summary.latency_expected_samples,
        MIN_VERDICT_PERCENT
    );
    println!("{}", serde_json::to_string(&summary)?);
    Ok(())
}

fn start_collector(
    mappings: BTreeMap<String, TopicMapping>,
    tracker: Arc<Mutex<LatencyTracker>>,
    semantics: SemanticsArg,
    stop: Arc<AtomicBool>,
) -> anyhow::Result<thread::JoinHandle<anyhow::Result<u64>>> {
    let (ready_tx, ready_rx) = mpsc::sync_channel(1);
    let handle = thread::spawn(move || {
        let setup = (|| -> anyhow::Result<(Node, stream::SelectAll<VerdictStream>)> {
            let context = Context::create()?;
            let mut node = Node::create(context, "mstlo_benchmark_latency", "")?;
            let mut streams = Vec::with_capacity(mappings.len());
            for (name, mapping) in mappings {
                let property_id = tracker
                    .lock()
                    .expect("latency tracker lock poisoned")
                    .property_id(&VarName::new(&name))
                    .expect("output property is registered");
                let subscription =
                    node.subscribe::<MstloTimedValue>(&mapping.topic, output_qos())?;
                streams.push(
                    Box::pin(subscription.map(move |message| (property_id, message)))
                        as VerdictStream,
                );
            }
            Ok((node, stream::select_all(streams)))
        })();

        let (mut node, mut verdicts) = match setup {
            Ok(setup) => {
                let _ = ready_tx.send(Ok(()));
                setup
            }
            Err(error) => {
                let _ = ready_tx.send(Err(error.to_string()));
                return Err(error);
            }
        };
        let mut invalid_outputs = 0_u64;
        while !stop.load(Ordering::Acquire) {
            node.spin_once(Duration::from_millis(2));
            drain_verdicts(&mut verdicts, &tracker, semantics, &mut invalid_outputs);
        }
        node.spin_once(Duration::ZERO);
        drain_verdicts(&mut verdicts, &tracker, semantics, &mut invalid_outputs);
        Ok(invalid_outputs)
    });
    ready_rx
        .recv()
        .map_err(|_| anyhow::anyhow!("ROS verdict collector stopped during setup"))?
        .map_err(anyhow::Error::msg)?;
    Ok(handle)
}

fn drain_verdicts(
    verdicts: &mut stream::SelectAll<VerdictStream>,
    tracker: &Arc<Mutex<LatencyTracker>>,
    semantics: SemanticsArg,
    invalid_outputs: &mut u64,
) {
    while let Some(Some((property_id, message))) = verdicts.next().now_or_never() {
        if !semantics.accepts_ros(&message) {
            *invalid_outputs = invalid_outputs.saturating_add(1);
            continue;
        }
        let Ok(seconds) = u64::try_from(message.time.sec) else {
            *invalid_outputs = invalid_outputs.saturating_add(1);
            continue;
        };
        if message.time.nanosec >= 1_000_000_000 {
            *invalid_outputs = invalid_outputs.saturating_add(1);
            continue;
        }
        let timestamp = Duration::new(seconds, message.time.nanosec);
        if let Ok(timestamp_ns) = timestamp.as_nanos().try_into() {
            tracker
                .lock()
                .expect("latency tracker lock poisoned")
                .record_output(property_id, timestamp_ns);
        } else {
            *invalid_outputs = invalid_outputs.saturating_add(1);
        }
    }
}

fn spin_until(node: &mut Node, deadline: Instant) {
    while Instant::now() < deadline {
        node.spin_once(Duration::ZERO);
        let remaining = deadline.saturating_duration_since(Instant::now());
        thread::sleep(remaining.min(Duration::from_millis(2)));
    }
}

fn input_topic(topic_namespace: &str, robot: usize, axis: &str) -> String {
    let topic_namespace = topic_namespace.trim_matches('/');
    if topic_namespace.is_empty() {
        format!("/mstlo/robot_{robot}/{axis}")
    } else {
        format!("/{topic_namespace}/mstlo/robot_{robot}/{axis}")
    }
}

#[cfg(test)]
mod tests {
    use super::input_topic;

    #[test]
    fn input_topics_use_the_benchmark_namespace() {
        assert_eq!(
            input_topic("mstlo_bench_run123", 7, "y"),
            "/mstlo_bench_run123/mstlo/robot_7/y"
        );
        assert_eq!(input_topic("", 7, "y"), "/mstlo/robot_7/y");
    }
}

fn input_qos() -> QosProfile {
    QosProfile::default()
        .keep_last(INPUT_DEPTH)
        .reliable()
        .volatile()
}

fn output_qos() -> QosProfile {
    QosProfile::default()
        .keep_last(OUTPUT_DEPTH)
        .reliable()
        .volatile()
}

fn message(time: RosDuration, value: f64) -> MstloTimedValue {
    MstloTimedValue {
        time,
        kind: FLOAT_KIND,
        float_value: value,
        bool_value: false,
        interval_lower: 0.0,
        interval_upper: 0.0,
    }
}
