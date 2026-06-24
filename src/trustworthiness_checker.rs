use std::{
    ffi::OsStr,
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
const TRUSTWORTHINESS_CHECKER_RUST_LOG: &str = "INFO";

#[derive(Resource)]
pub struct TrustworthinessCheckerProcesses {
    children: Vec<Child>,
}

impl TrustworthinessCheckerProcesses {
    pub fn none() -> Self {
        Self {
            children: Vec::new(),
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
        let mut children = Vec::with_capacity(config.robots + 1);

        children.push(spawn_scheduler(args, config, &bundle)?);
        for robot_index in 0..config.robots {
            children.push(spawn_worker(args, config, &bundle, robot_index)?);
        }

        Ok(Self { children })
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
    input_map: PathBuf,
    output_map: PathBuf,
    graph: PathBuf,
    log_dir: PathBuf,
    tracing_log_dir: PathBuf,
    ros_setup: Option<PathBuf>,
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

        let spec = artifact_dir.join("quadrant_pose2d.dsrv");
        let input_map = artifact_dir.join("quadrant_pose2d_ros_in.json");
        let output_map = artifact_dir.join("quadrant_pose2d_ros_out.json");
        let graph = artifact_dir.join("quadrant_distribution_graph.json");
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

        write_file(&spec, &generate_spec(config))?;
        write_file(&input_map, &generate_input_map(config))?;
        write_file(&output_map, &generate_output_map(config))?;
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
            input_map,
            output_map,
            graph,
            log_dir,
            tracing_log_dir,
            ros_setup,
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

fn spawn_scheduler(
    args: &Args,
    config: &SimulationConfig,
    bundle: &TrustworthinessCheckerBundle,
) -> Result<Child, String> {
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
    for robot_index in 0..config.robots {
        command.arg(dist_constraint_name(robot_index));
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
        .arg("--ros-dist-graph-topic")
        .arg(&args.trustworthiness_checker_dist_graph_topic)
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

fn spawn_worker(
    args: &Args,
    config: &SimulationConfig,
    bundle: &TrustworthinessCheckerBundle,
    robot_index: usize,
) -> Result<Child, String> {
    let node = node_name(robot_index);
    let mut command = checker_command(bundle);
    command
        .arg(&bundle.spec)
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
    let Some(setup) = &bundle.ros_setup else {
        command.env("IDL_PACKAGE_FILTER", IDL_PACKAGE_FILTER);
        command.env("RUST_LOG", TRUSTWORTHINESS_CHECKER_RUST_LOG);
        return Ok(());
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

    for entry in output.stdout.split(|byte| *byte == 0) {
        if entry.is_empty() {
            continue;
        }
        let Some(eq_index) = entry.iter().position(|byte| *byte == b'=') else {
            continue;
        };
        let key = OsStr::from_bytes(&entry[..eq_index]);
        let value = OsStr::from_bytes(&entry[eq_index + 1..]);
        command.env(key, value);
    }
    command.env("IDL_PACKAGE_FILTER", IDL_PACKAGE_FILTER);
    command.env("RUST_LOG", TRUSTWORTHINESS_CHECKER_RUST_LOG);

    Ok(())
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
        .and_then(|_| writeln!(file, "rust_log: {TRUSTWORTHINESS_CHECKER_RUST_LOG}"))
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
    spec.push('\n');

    for robot_index in 0..config.robots {
        spec.push_str(&format!("out {}: Bool\n", trust_var(robot_index)));
    }
    for robot_index in 0..config.robots {
        spec.push_str(&format!(
            "out {}: Bool\n",
            dist_constraint_name(robot_index)
        ));
    }
    spec.push('\n');

    for robot_index in 0..config.robots {
        for quadrant in Quadrant::ALL {
            spec.push_str(&format!("aux {}\n", quadrant_var(robot_index, quadrant)));
        }
        for other_index in 0..config.robots {
            spec.push_str(&format!(
                "aux {}\n",
                same_quadrant_var(robot_index, other_index)
            ));
        }
    }
    spec.push('\n');

    let half_width = config.arena_width * 0.5;
    let half_height = config.arena_height * 0.5;
    for robot_index in 0..config.robots {
        let pose = pose_var(robot_index);
        spec.push_str(&format!(
            "{} = {}.x >= 0.0 && {}.y >= 0.0\n",
            quadrant_var(robot_index, Quadrant::Ne),
            pose,
            pose
        ));
        spec.push_str(&format!(
            "{} = {}.x < 0.0 && {}.y >= 0.0\n",
            quadrant_var(robot_index, Quadrant::Nw),
            pose,
            pose
        ));
        spec.push_str(&format!(
            "{} = {}.x < 0.0 && {}.y < 0.0\n",
            quadrant_var(robot_index, Quadrant::Sw),
            pose,
            pose
        ));
        spec.push_str(&format!(
            "{} = {}.x >= 0.0 && {}.y < 0.0\n",
            quadrant_var(robot_index, Quadrant::Se),
            pose,
            pose
        ));
        spec.push_str(&format!(
            "{} = abs({}.x) <= {:.3} && abs({}.y) <= {:.3}\n",
            trust_var(robot_index),
            pose,
            half_width,
            pose,
            half_height
        ));
    }
    spec.push('\n');

    for robot_index in 0..config.robots {
        for other_index in 0..config.robots {
            let clauses = Quadrant::ALL
                .iter()
                .map(|quadrant| {
                    format!(
                        "({} && {})",
                        quadrant_var(robot_index, *quadrant),
                        quadrant_var(other_index, *quadrant)
                    )
                })
                .collect::<Vec<_>>()
                .join(" || ");
            spec.push_str(&format!(
                "{} = {}\n",
                same_quadrant_var(robot_index, other_index),
                clauses
            ));
        }
    }
    spec.push('\n');

    for robot_index in 0..config.robots {
        spec.push_str(&format!(
            "{} = {}\n",
            dist_constraint_name(robot_index),
            distribution_constraint_expr(config, robot_index)
        ));
    }

    spec
}

fn distribution_constraint_expr(config: &SimulationConfig, robot_index: usize) -> String {
    let mut candidate_order = (0..config.robots)
        .filter(|candidate| *candidate != robot_index)
        .collect::<Vec<_>>();
    candidate_order.push(robot_index);

    let mut expr = format!("monitored_at({}, \"None\")", trust_var(robot_index));
    for candidate in candidate_order.into_iter().rev() {
        expr = format!(
            "if {} then monitored_at({}, \"{}\") else {}",
            same_quadrant_var(robot_index, candidate),
            trust_var(robot_index),
            node_name(candidate),
            expr
        );
    }
    expr
}

fn generate_input_map(config: &SimulationConfig) -> String {
    let entries = (0..config.robots)
        .map(|robot_index| {
            format!(
                "  \"{}\": {{ \"topic\": \"/robot_{}/pose2d\", \"msg_type\": \"Pose2D\" }}",
                pose_var(robot_index),
                robot_index
            )
        })
        .collect::<Vec<_>>()
        .join(",\n");
    format!("{{\n{}\n}}\n", entries)
}

fn generate_output_map(config: &SimulationConfig) -> String {
    let entries = (0..config.robots)
        .map(|robot_index| {
            format!(
                "  \"{}\": {{ \"topic\": \"/{}/trustworthy\", \"msg_type\": \"Bool\" }}",
                trust_var(robot_index),
                node_name(robot_index)
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
        var_names.push(trust_var(robot_index));
        var_names.push(dist_constraint_name(robot_index));
        for quadrant in Quadrant::ALL {
            var_names.push(quadrant_var(robot_index, quadrant));
        }
        for other_index in 0..config.robots {
            var_names.push(same_quadrant_var(robot_index, other_index));
        }
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
        labels.push_str(&format!(
            "      \"{}\",\n      \"{}\"\n    ]",
            pose_var(robot_index),
            trust_var(robot_index)
        ));
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

#[derive(Clone, Copy)]
enum Quadrant {
    Ne,
    Nw,
    Sw,
    Se,
}

impl Quadrant {
    const ALL: [Quadrant; 4] = [Quadrant::Ne, Quadrant::Nw, Quadrant::Sw, Quadrant::Se];

    fn suffix(self) -> &'static str {
        match self {
            Quadrant::Ne => "NE",
            Quadrant::Nw => "NW",
            Quadrant::Sw => "SW",
            Quadrant::Se => "SE",
        }
    }
}

fn node_name(robot_index: usize) -> String {
    format!("R{}", robot_index + 1)
}

fn pose_var(robot_index: usize) -> String {
    format!("{}Pose", var_prefix(robot_index))
}

fn trust_var(robot_index: usize) -> String {
    format!("{}Trustworthy", var_prefix(robot_index))
}

fn dist_constraint_name(robot_index: usize) -> String {
    format!("dist{}", robot_index + 1)
}

fn quadrant_var(robot_index: usize, quadrant: Quadrant) -> String {
    format!("{}In{}", var_prefix(robot_index), quadrant.suffix())
}

fn same_quadrant_var(robot_index: usize, other_index: usize) -> String {
    format!(
        "{}SameQuadrantAs{}",
        var_prefix(robot_index),
        node_name(other_index)
    )
}

fn var_prefix(robot_index: usize) -> String {
    format!("r{}", robot_index + 1)
}
