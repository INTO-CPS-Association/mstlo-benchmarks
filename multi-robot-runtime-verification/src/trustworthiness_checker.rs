use std::{
    ffi::{OsStr, OsString},
    fs::{self, File},
    io::Write,
    os::unix::ffi::OsStrExt,
    path::{Path, PathBuf},
    process::{self, Child, Command, Stdio},
    time::{SystemTime, UNIX_EPOCH},
};

use bevy::prelude::Resource;

use crate::{config::Args, simulation::SimulationConfig};

const IDL_PACKAGE_FILTER: &str =
    "std_msgs;geometry_msgs;nav_msgs;id_pose_msgs;robo_sapiens_interfaces";
const PROPERTY_EMULATOR_SCRIPT: &str = concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/assets/properties_emulator/properties_pub.py"
);
const PROPERTY_EMULATOR_CONFIG: &str = concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/assets/properties_emulator/config.yaml"
);

#[derive(Resource)]
pub struct TrustworthinessCheckerProcesses {
    children: Vec<Child>,
    run_dir: Option<PathBuf>,
}

impl TrustworthinessCheckerProcesses {
    pub fn none() -> Self {
        Self {
            children: Vec::new(),
            run_dir: None,
        }
    }

    pub fn start(args: &Args, config: &SimulationConfig) -> Result<Self, String> {
        if !args.trustworthiness_checker {
            return Ok(Self::none());
        }
        if args.no_ros {
            return Err(
                "--trustworthiness-checker requires ROS publishing; remove --no-ros".to_string(),
            );
        }
        if !args.trustworthiness_checker_dir.is_dir() {
            return Err(format!(
                "trustworthiness checker directory does not exist: {}",
                args.trustworthiness_checker_dir.display()
            ));
        }

        let bundle = TrustworthinessCheckerBundle::write(args, config)?;
        prebuild_checker(args, &bundle)?;
        let mut children = Vec::with_capacity(config.robots + 2);

        children.push(spawn_property_emulator(&bundle)?);
        for robot_index in 0..config.robots {
            children.push(spawn_worker(args, config, &bundle, robot_index)?);
        }
        children.push(spawn_scheduler(args, &bundle)?);

        Ok(Self {
            children,
            run_dir: Some(bundle.run_dir),
        })
    }

    pub fn child_pids(&self) -> Vec<u32> {
        self.children.iter().map(Child::id).collect()
    }

    pub fn run_dir(&self) -> Option<&Path> {
        self.run_dir.as_deref()
    }
}

impl Drop for TrustworthinessCheckerProcesses {
    fn drop(&mut self) {
        for child in &mut self.children {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

struct TrustworthinessCheckerBundle {
    run_dir: PathBuf,
    checker_dir: PathBuf,
    binary: PathBuf,
    spec: PathBuf,
    worker_bootstrap_spec: PathBuf,
    input_map: PathBuf,
    output_map: PathBuf,
    graph: PathBuf,
    property_emulator_script: PathBuf,
    property_emulator_config: PathBuf,
    log_dir: PathBuf,
    tracing_log_dir: PathBuf,
    ros_setup: Option<PathBuf>,
    ros_env: Vec<(OsString, OsString)>,
    rust_log: String,
}

impl TrustworthinessCheckerBundle {
    fn write(args: &Args, config: &SimulationConfig) -> Result<Self, String> {
        fs::create_dir_all(&args.trustworthiness_checker_work_dir).map_err(|err| {
            format!(
                "failed to create trustworthiness checker work directory {}: {err}",
                args.trustworthiness_checker_work_dir.display()
            )
        })?;

        let root_dir = fs::canonicalize(&args.trustworthiness_checker_work_dir).map_err(|err| {
            format!(
                "failed to resolve trustworthiness checker work directory {}: {err}",
                args.trustworthiness_checker_work_dir.display()
            )
        })?;

        let run_dir = root_dir.join(format!("run-{}-{}", unix_timestamp_secs()?, process::id()));
        let artifact_dir = run_dir.join("artifacts");
        let log_dir = run_dir.join("logs");
        let tracing_log_dir = log_dir.join("tracing");
        fs::create_dir_all(&artifact_dir).map_err(|err| {
            format!(
                "failed to create artifact directory {}: {err}",
                artifact_dir.display()
            )
        })?;
        fs::create_dir_all(&log_dir).map_err(|err| {
            format!(
                "failed to create log directory {}: {err}",
                log_dir.display()
            )
        })?;
        fs::create_dir_all(&tracing_log_dir).map_err(|err| {
            format!(
                "failed to create tracing log directory {}: {err}",
                tracing_log_dir.display()
            )
        })?;

        let spec = artifact_dir.join("machine_properties.dsrv");
        let worker_bootstrap_spec = artifact_dir.join("worker_bootstrap_empty.dsrv");
        let input_map = artifact_dir.join("machine_properties_ros_in.json");
        let output_map = artifact_dir.join("machine_properties_ros_out.json");
        let graph = artifact_dir.join("machine_property_distribution_graph.json");
        let property_emulator_script = PathBuf::from(PROPERTY_EMULATOR_SCRIPT);
        if !property_emulator_script.is_file() {
            return Err(format!(
                "bundled property emulator script not found: {}",
                property_emulator_script.display()
            ));
        }
        let property_emulator_config = PathBuf::from(PROPERTY_EMULATOR_CONFIG);
        if !property_emulator_config.is_file() {
            return Err(format!(
                "bundled property emulator config not found: {}",
                property_emulator_config.display()
            ));
        }
        let checker_dir = fs::canonicalize(&args.trustworthiness_checker_dir).map_err(|err| {
            format!(
                "failed to resolve trustworthiness checker directory {}: {err}",
                args.trustworthiness_checker_dir.display()
            )
        })?;
        let binary = checker_dir
            .join("target")
            .join(profile_target_dir(&args.trustworthiness_checker_profile))
            .join("trustworthiness_checker");
        let ros_setup = if args.trustworthiness_checker_ros_setup.is_file() {
            Some(
                fs::canonicalize(&args.trustworthiness_checker_ros_setup).map_err(|err| {
                    format!(
                        "failed to resolve trustworthiness checker ROS setup {}: {err}",
                        args.trustworthiness_checker_ros_setup.display()
                    )
                })?,
            )
        } else {
            eprintln!(
                "INFO trustworthiness checker ROS setup not found, using current environment only: {}",
                args.trustworthiness_checker_ros_setup.display()
            );
            None
        };
        let ros_env = load_ros_setup_env(ros_setup.as_deref())?;

        write_file(&spec, &generate_spec(config))?;
        write_file(&worker_bootstrap_spec, generate_worker_bootstrap_spec())?;
        write_file(&input_map, &generate_input_map(config))?;
        write_file(&output_map, &generate_output_map())?;
        write_file(&graph, &generate_distribution_graph(config))?;

        eprintln!(
            "INFO trustworthiness checker run directory: {}",
            run_dir.display()
        );

        Ok(Self {
            run_dir,
            checker_dir,
            binary,
            spec,
            worker_bootstrap_spec,
            input_map,
            output_map,
            graph,
            property_emulator_script,
            property_emulator_config,
            log_dir,
            tracing_log_dir,
            ros_setup,
            ros_env,
            rust_log: args.trustworthiness_checker_rust_log.clone(),
        })
    }
}

fn prebuild_checker(args: &Args, bundle: &TrustworthinessCheckerBundle) -> Result<(), String> {
    let mut command = Command::new("cargo");
    command
        .current_dir(&bundle.checker_dir)
        .arg("build")
        .arg("--profile")
        .arg(&args.trustworthiness_checker_profile)
        .arg("--features")
        .arg("ros")
        .arg("--bin")
        .arg("trustworthiness_checker");

    run(
        command,
        "trustworthiness checker prebuild",
        bundle,
        "prebuild",
    )?;

    if !bundle.binary.is_file() {
        return Err(format!(
            "trustworthiness checker prebuild completed but binary was not found: {}",
            bundle.binary.display()
        ));
    }

    Ok(())
}

fn spawn_scheduler(args: &Args, bundle: &TrustworthinessCheckerBundle) -> Result<Child, String> {
    let mut command = checker_command(bundle);
    command
        .arg(&bundle.spec)
        .arg("--runtime")
        .arg("distributed")
        .arg("--semantics")
        .arg("untimed")
        .arg("--distribution-graph")
        .arg(&bundle.graph)
        .arg("--distribution-constraints");
    for property in MachineProperty::ALL {
        command.arg(dist_constraint_name(property));
    }
    command
        .arg("--scheduling-mode")
        .arg("ros")
        .arg("--dist-constraint-solver")
        .arg("sat")
        .arg("--scheduler-ros-node-name")
        .arg("tc_scheduler_main")
        .arg("--scheduler-reconf-topic")
        .arg(&args.trustworthiness_checker_reconf_topic)
        .arg("--input-ros-file")
        .arg(&bundle.input_map)
        .arg("--output-ros-file")
        .arg(&bundle.output_map)
        .arg("--log-file")
        .arg(tracing_log_path(bundle, "scheduler"));

    spawn(
        command,
        "trustworthiness checker scheduler",
        bundle,
        "scheduler",
    )
}

fn spawn_property_emulator(bundle: &TrustworthinessCheckerBundle) -> Result<Child, String> {
    let mut command = Command::new("python3");
    command
        .arg(&bundle.property_emulator_script)
        .arg("--config")
        .arg(&bundle.property_emulator_config)
        .arg("--log-level")
        .arg("WARN");

    spawn(command, "property emulator", bundle, "property_emulator")
}

fn spawn_worker(
    args: &Args,
    config: &SimulationConfig,
    bundle: &TrustworthinessCheckerBundle,
    robot_index: usize,
) -> Result<Child, String> {
    let node = node_name(robot_index);
    let mut command = checker_command(bundle);
    command
        .arg(&bundle.worker_bootstrap_spec)
        .arg("--runtime")
        .arg("reconf-semi-sync")
        .arg("--distribution-graph")
        .arg(&bundle.graph)
        .arg("--local-node")
        .arg(&node)
        .arg("--reconf-topic")
        .arg(format!(
            "{}_{}",
            args.trustworthiness_checker_reconf_topic, node
        ))
        .arg("--input-ros-file")
        .arg(&bundle.input_map)
        .arg("--output-ros-file")
        .arg(&bundle.output_map)
        .arg("--log-file")
        .arg(tracing_log_path(bundle, &format!("worker_{}", robot_index)));

    if config.robots == 0 {
        return Err("cannot launch trustworthiness checker workers without robots".to_string());
    }

    spawn(
        command,
        &format!("trustworthiness checker worker {node}"),
        bundle,
        &format!("worker_{}", robot_index),
    )
}

fn checker_command(bundle: &TrustworthinessCheckerBundle) -> Command {
    let mut command = Command::new(&bundle.binary);
    command.current_dir(&bundle.checker_dir);
    command
}

fn tracing_log_path(bundle: &TrustworthinessCheckerBundle, stem: &str) -> PathBuf {
    bundle.tracing_log_dir.join(format!("{stem}.tracing.log"))
}

fn run(
    mut command: Command,
    description: &str,
    bundle: &TrustworthinessCheckerBundle,
    log_stem: &str,
) -> Result<(), String> {
    apply_ros_setup_env(&mut command, bundle)?;
    let formatted = format_command(&command);
    eprintln!("INFO {description}: {formatted}");
    command
        .stdout(log_file(
            bundle,
            log_stem,
            "stdout",
            description,
            &formatted,
        )?)
        .stderr(log_file(
            bundle,
            log_stem,
            "stderr",
            description,
            &formatted,
        )?);
    let status = command
        .status()
        .map_err(|err| format!("failed to run {description}: {err}"))?;
    if !status.success() {
        return Err(format!(
            "{description} failed with {status}; see logs in {}",
            bundle.log_dir.display()
        ));
    }
    Ok(())
}

fn spawn(
    mut command: Command,
    description: &str,
    bundle: &TrustworthinessCheckerBundle,
    log_stem: &str,
) -> Result<Child, String> {
    apply_ros_setup_env(&mut command, bundle)?;
    let formatted = format_command(&command);
    eprintln!("INFO {description}: {formatted}");
    command
        .stdout(log_file(
            bundle,
            log_stem,
            "stdout",
            description,
            &formatted,
        )?)
        .stderr(log_file(
            bundle,
            log_stem,
            "stderr",
            description,
            &formatted,
        )?);
    command
        .spawn()
        .map_err(|err| format!("failed to spawn {description}: {err}"))
}

fn apply_ros_setup_env(
    command: &mut Command,
    bundle: &TrustworthinessCheckerBundle,
) -> Result<(), String> {
    for (key, value) in &bundle.ros_env {
        command.env(key, value);
    }
    command.env("IDL_PACKAGE_FILTER", IDL_PACKAGE_FILTER);
    command.env("RUST_LOG", &bundle.rust_log);

    Ok(())
}

fn load_ros_setup_env(setup: Option<&Path>) -> Result<Vec<(OsString, OsString)>, String> {
    let Some(setup) = setup else {
        return Ok(Vec::new());
    };
    let output = Command::new("bash")
        .arg("-lc")
        .arg(format!(
            "source {} && env -0",
            shell_word(setup.as_os_str())
        ))
        .output()
        .map_err(|err| {
            format!(
                "failed to source trustworthiness checker ROS setup {}: {err}",
                setup.display()
            )
        })?;

    if !output.status.success() {
        return Err(format!(
            "failed to source trustworthiness checker ROS setup {}: {}",
            setup.display(),
            String::from_utf8_lossy(&output.stderr)
        ));
    }

    let mut env = Vec::new();
    for entry in output.stdout.split(|byte| *byte == 0) {
        if entry.is_empty() {
            continue;
        }
        let Some(eq_index) = entry.iter().position(|byte| *byte == b'=') else {
            continue;
        };
        let key = OsStr::from_bytes(&entry[..eq_index]);
        let value = OsStr::from_bytes(&entry[eq_index + 1..]);
        env.push((key.to_os_string(), value.to_os_string()));
    }

    Ok(env)
}

fn profile_target_dir(profile: &str) -> &str {
    match profile {
        "dev" => "debug",
        "release" => "release",
        profile => profile,
    }
}

fn format_command(command: &Command) -> String {
    let mut parts = Vec::new();
    if let Some(dir) = command.get_current_dir() {
        parts.push("cd".to_string());
        parts.push(shell_word(dir.as_os_str()));
        parts.push("&&".to_string());
    }
    parts.push(shell_word(command.get_program()));
    parts.extend(command.get_args().map(shell_word));
    parts.join(" ")
}

fn shell_word(value: &OsStr) -> String {
    let text = value.to_string_lossy();
    if text
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '/' | '.' | '_' | '-' | ':' | '='))
    {
        text.into_owned()
    } else {
        format!("'{}'", text.replace('\'', "'\\''"))
    }
}

fn log_file(
    bundle: &TrustworthinessCheckerBundle,
    stem: &str,
    stream: &str,
    description: &str,
    command: &str,
) -> Result<Stdio, String> {
    let name = format!("{stem}.{stream}.log");
    let path = bundle.log_dir.join(&name);
    let mut file = File::create(&path).map_err(|err| {
        format!(
            "failed to create trustworthiness checker log {}: {err}",
            path.display()
        )
    })?;
    writeln!(file, "# Trust checker process log")
        .and_then(|_| writeln!(file, "description: {description}"))
        .and_then(|_| writeln!(file, "run_dir: {}", bundle.run_dir.display()))
        .and_then(|_| {
            writeln!(
                file,
                "ros_setup: {}",
                bundle
                    .ros_setup
                    .as_ref()
                    .map(|path| path.display().to_string())
                    .unwrap_or_else(|| "<current environment only>".to_string())
            )
        })
        .and_then(|_| writeln!(file, "idl_package_filter: {IDL_PACKAGE_FILTER}"))
        .and_then(|_| writeln!(file, "rust_log: {}", bundle.rust_log))
        .and_then(|_| writeln!(file, "stream: {stream}"))
        .and_then(|_| writeln!(file, "command: {command}"))
        .and_then(|_| writeln!(file))
        .map_err(|err| {
            format!("failed to write trustworthiness checker log header {name}: {err}")
        })?;
    Ok(Stdio::from(file))
}

fn write_file(path: &Path, contents: &str) -> Result<(), String> {
    let mut file =
        File::create(path).map_err(|err| format!("failed to create {}: {err}", path.display()))?;
    file.write_all(contents.as_bytes())
        .map_err(|err| format!("failed to write {}: {err}", path.display()))
}

fn generate_worker_bootstrap_spec() -> &'static str {
    ""
}

fn unix_timestamp_secs() -> Result<u64, String> {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .map_err(|err| format!("system clock is before UNIX epoch: {err}"))
}

fn generate_spec(config: &SimulationConfig) -> String {
    let mut spec = String::new();
    for robot_index in 0..config.robots {
        spec.push_str(&format!(
            "in {}: Struct<x: Float, y: Float, theta: Float>\n",
            pose_var(robot_index)
        ));
    }
    for property in MachineProperty::ALL {
        spec.push_str(&format!("in {}: Int\n", property.input_var()));
    }
    spec.push('\n');

    for property in MachineProperty::ALL {
        spec.push_str(&format!("out {}: Bool\n", property.predicate_var()));
    }
    for property in MachineProperty::ALL {
        spec.push_str(&format!("out {}: Bool\n", dist_constraint_name(property)));
    }
    for robot_index in 0..config.robots {
        for property in MachineProperty::ALL {
            spec.push_str(&format!(
                "aux {}: Bool\n",
                bounding_area_var(robot_index, property)
            ));
        }
    }
    spec.push('\n');

    for property in MachineProperty::ALL {
        spec.push_str(&format!(
            "{} = {}\n",
            property.predicate_var(),
            property.predicate_expr()
        ));
    }
    spec.push('\n');

    for robot_index in 0..config.robots {
        for property in MachineProperty::ALL {
            spec.push_str(&format!(
                "{} = {}\n",
                bounding_area_var(robot_index, property),
                bounding_area_expr(robot_index, property)
            ));
        }
    }
    spec.push('\n');

    for property in MachineProperty::ALL {
        spec.push_str(&format!(
            "{} = {}\n",
            dist_constraint_name(property),
            distribution_constraint_expr(config, property)
        ));
    }

    spec
}

fn distribution_constraint_expr(config: &SimulationConfig, property: MachineProperty) -> String {
    let predicate_var = property.predicate_var();
    if config.robots == 0 {
        return "true".to_string();
    }

    let candidates = (0..config.robots)
        .map(|candidate| {
            format!(
                "({} && monitored_at({}, \"{}\"))",
                bounding_area_var(candidate, property),
                predicate_var,
                node_name(candidate)
            )
        })
        .collect::<Vec<_>>();

    let any_candidate = (0..config.robots)
        .map(|candidate| bounding_area_var(candidate, property))
        .collect::<Vec<_>>()
        .join(" || ");

    format!(
        "(if ({}) then ({}) else true)",
        any_candidate,
        candidates.join(" || ")
    )
}

fn generate_input_map(config: &SimulationConfig) -> String {
    let mut entries = (0..config.robots)
        .map(|robot_index| {
            format!(
                "  \"{}\": {{ \"topic\": \"/robot_{}/pose2d\", \"msg_type\": \"Pose2D\" }}",
                pose_var(robot_index),
                robot_index
            )
        })
        .collect::<Vec<_>>();
    entries.extend(MachineProperty::ALL.iter().map(|property| {
        format!(
            "  \"{}\": {{ \"topic\": \"/{}\", \"msg_type\": \"Int32\" }}",
            property.input_var(),
            property.input_var()
        )
    }));
    format!("{{\n{}\n}}\n", entries.join(",\n"))
}

fn generate_output_map() -> String {
    let entries = MachineProperty::ALL
        .iter()
        .map(|property| {
            format!(
                "  \"{}\": {{ \"topic\": \"/properties/{}/predicate\", \"msg_type\": \"Bool\" }}",
                property.predicate_var(),
                property.topic_name()
            )
        })
        .collect::<Vec<_>>()
        .join(",\n");
    format!("{{\n{}\n}}\n", entries)
}

fn generate_distribution_graph(config: &SimulationConfig) -> String {
    let nodes = std::iter::once("None".to_string())
        .chain((0..config.robots).map(node_name))
        .map(|node| format!("        \"{}\"", node))
        .collect::<Vec<_>>()
        .join(",\n");

    let edges = (0..config.robots)
        .map(|robot_index| format!("        [0, {}, 0]", robot_index + 1))
        .collect::<Vec<_>>()
        .join(",\n");

    let mut var_names = Vec::new();
    for robot_index in 0..config.robots {
        var_names.push(pose_var(robot_index));
        for property in MachineProperty::ALL {
            var_names.push(bounding_area_var(robot_index, property));
        }
    }
    for property in MachineProperty::ALL {
        var_names.push(property.input_var().to_string());
        var_names.push(property.predicate_var().to_string());
        var_names.push(dist_constraint_name(property));
    }
    let var_names = var_names
        .into_iter()
        .map(|var| format!("    \"{}\"", var))
        .collect::<Vec<_>>()
        .join(",\n");

    let mut labels = String::from("    \"0\": []");
    for robot_index in 0..config.robots {
        labels.push_str(",\n");
        labels.push_str(&format!("    \"{}\": [\n", robot_index + 1));
        labels.push_str(&format!("      \"{}\"\n    ]", pose_var(robot_index)));
    }

    format!(
        concat!(
            "{{\n",
            "  \"dist_graph\": {{\n",
            "    \"central_monitor\": 0,\n",
            "    \"graph\": {{\n",
            "      \"nodes\": [\n{}\n      ],\n",
            "      \"edge_property\": \"directed\",\n",
            "      \"edges\": [\n{}\n      ]\n",
            "    }}\n",
            "  }},\n",
            "  \"var_names\": [\n{}\n  ],\n",
            "  \"node_labels\": {{\n{}\n  }}\n",
            "}}\n"
        ),
        nodes, edges, var_names, labels
    )
}

fn bounding_area_expr(robot_index: usize, property: MachineProperty) -> String {
    let pose = pose_var(robot_index);
    let (x, y) = property.center();
    format!(
        "({} <= 5.0 && {} <= 5.0)",
        distance_from_center_expr(&format!("{pose}.x"), x),
        distance_from_center_expr(&format!("{pose}.y"), y)
    )
}

fn bounding_area_var(robot_index: usize, property: MachineProperty) -> String {
    format!("ba{}{}", node_name(robot_index), property.short_name())
}

fn distance_from_center_expr(value: &str, center: f64) -> String {
    if center < 0.0 {
        format!("abs({value} + {})", format_float(-center))
    } else {
        format!("abs({value} - {})", format_float(center))
    }
}

fn format_float(value: f64) -> String {
    if value.fract() == 0.0 {
        format!("{value:.1}")
    } else {
        value.to_string()
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum MachineProperty {
    ConveyorSystem,
    StackerCrane,
    VerticalLift,
    HorizontalCarousel,
}

impl MachineProperty {
    pub const ALL: [MachineProperty; 4] = [
        MachineProperty::ConveyorSystem,
        MachineProperty::StackerCrane,
        MachineProperty::VerticalLift,
        MachineProperty::HorizontalCarousel,
    ];

    pub fn input_var(self) -> &'static str {
        match self {
            MachineProperty::ConveyorSystem => "ConveyorSystem",
            MachineProperty::StackerCrane => "StackerCrane",
            MachineProperty::VerticalLift => "VerticalLift",
            MachineProperty::HorizontalCarousel => "HorizontalCarousel",
        }
    }

    pub fn predicate_var(self) -> &'static str {
        match self {
            MachineProperty::ConveyorSystem => "CPred",
            MachineProperty::StackerCrane => "SPred",
            MachineProperty::VerticalLift => "VPred",
            MachineProperty::HorizontalCarousel => "HPred",
        }
    }

    fn predicate_expr(self) -> &'static str {
        match self {
            MachineProperty::ConveyorSystem => "ConveyorSystem > 0",
            MachineProperty::StackerCrane => "StackerCrane > 0 && StackerCrane < 30",
            MachineProperty::VerticalLift => "VerticalLift < 100",
            MachineProperty::HorizontalCarousel => "HorizontalCarousel == 0",
        }
    }

    pub fn center(self) -> (f64, f64) {
        match self {
            MachineProperty::ConveyorSystem => (3.5, 3.0),
            MachineProperty::StackerCrane => (3.5, -6.0),
            MachineProperty::VerticalLift => (-4.0, -6.0),
            MachineProperty::HorizontalCarousel => (-4.0, 3.0),
        }
    }

    pub fn short_name(self) -> &'static str {
        match self {
            MachineProperty::ConveyorSystem => "C",
            MachineProperty::StackerCrane => "S",
            MachineProperty::VerticalLift => "V",
            MachineProperty::HorizontalCarousel => "H",
        }
    }

    fn topic_name(self) -> &'static str {
        match self {
            MachineProperty::ConveyorSystem => "conveyor_system",
            MachineProperty::StackerCrane => "stacker_crane",
            MachineProperty::VerticalLift => "vertical_lift",
            MachineProperty::HorizontalCarousel => "horizontal_carousel",
        }
    }
}

fn node_name(robot_index: usize) -> String {
    format!("R{}", robot_index + 1)
}

fn pose_var(robot_index: usize) -> String {
    format!("{}Pose", var_prefix(robot_index))
}

fn dist_constraint_name(property: MachineProperty) -> String {
    format!("dist{}", property.predicate_var())
}

fn var_prefix(robot_index: usize) -> String {
    format!("r{}", robot_index + 1)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn config(robots: usize) -> SimulationConfig {
        SimulationConfig {
            robots,
            seed: 42,
            arena_min_x: -7.0,
            arena_min_y: -10.5,
            arena_width: 32.0,
            arena_height: 19.2,
            brownian_scale: 0.4,
            sim_hz: 60.0,
            publish_rate_hz: 10.0,
            robot_radius: 0.12,
            robot_labels: false,
            screenshot: false,
            wall_avoidance_margin: 1.0,
            wall_avoidance_strength: 2.0,
            render_scale: 60.0,
            trustworthiness_checker_reconf_topic: "reconfig".to_string(),
        }
    }

    #[test]
    fn generated_spec_uses_four_machine_properties() {
        let spec = generate_spec(&config(3));

        for var in ["CPred", "SPred", "VPred", "HPred"] {
            assert!(spec.contains(&format!("out {var}: Bool")));
        }
        for constraint in ["distCPred", "distSPred", "distVPred", "distHPred"] {
            assert!(spec.contains(&format!("out {constraint}: Bool")));
        }
        assert!(spec.contains("CPred = ConveyorSystem > 0"));
        assert!(spec.contains("SPred = StackerCrane > 0 && StackerCrane < 30"));
        assert!(spec.contains("VPred = VerticalLift < 100"));
        assert!(spec.contains("HPred = HorizontalCarousel == 0"));
        assert!(!spec.contains("neTrustworthy"));
    }

    #[test]
    fn distribution_constraint_targets_matching_bounding_area_nodes() {
        let spec = generate_spec(&config(2));

        assert!(spec.contains("aux baR1C: Bool"));
        assert!(spec.contains("aux baR2V: Bool"));
        assert!(
            spec.contains("baR1C = (abs(r1Pose.x - 3.5) <= 5.0 && abs(r1Pose.y - 3.0) <= 5.0)")
        );
        assert!(
            spec.contains("baR2V = (abs(r2Pose.x + 4.0) <= 5.0 && abs(r2Pose.y + 6.0) <= 5.0)")
        );
        assert!(spec.contains(
            "distCPred = (if (baR1C || baR2C) then ((baR1C && monitored_at(CPred, \"R1\")) || (baR2C && monitored_at(CPred, \"R2\"))) else true)"
        ));
        assert!(spec.contains(
            "distVPred = (if (baR1V || baR2V) then ((baR1V && monitored_at(VPred, \"R1\")) || (baR2V && monitored_at(VPred, \"R2\"))) else true)"
        ));
    }

    #[test]
    fn distribution_graph_does_not_preassign_machine_inputs() {
        let graph = generate_distribution_graph(&config(2));

        assert!(graph.contains("\"0\": []"));
        assert!(graph.contains("\"1\": [\n      \"r1Pose\"\n    ]"));
        assert!(graph.contains("\"2\": [\n      \"r2Pose\"\n    ]"));
        assert!(graph.contains("\"ConveyorSystem\""));
        assert!(graph.contains("\"baR1C\""));
        assert!(graph.contains("\"baR2V\""));
        assert!(!graph.contains("\"0\": [\n      \"ConveyorSystem\""));
    }
}
