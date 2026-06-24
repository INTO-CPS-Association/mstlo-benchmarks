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

        children.push(spawn_scheduler(args, &bundle)?);
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
    worker_bootstrap_spec: PathBuf,
    input_map: PathBuf,
    output_map: PathBuf,
    graph: PathBuf,
    log_dir: PathBuf,
    tracing_log_dir: PathBuf,
    ros_setup: Option<PathBuf>,
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

        let spec = artifact_dir.join("quadrant_pose2d.dsrv");
        let worker_bootstrap_spec = artifact_dir.join("worker_bootstrap_empty.dsrv");
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
            log_dir,
            tracing_log_dir,
            ros_setup,
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
    for quadrant in Quadrant::ALL {
        command.arg(dist_constraint_name(quadrant));
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
    let Some(setup) = &bundle.ros_setup else {
        command.env("IDL_PACKAGE_FILTER", IDL_PACKAGE_FILTER);
        command.env("RUST_LOG", &bundle.rust_log);
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
    command.env("RUST_LOG", &bundle.rust_log);

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
    spec.push('\n');

    for quadrant in Quadrant::ALL {
        spec.push_str(&format!("out {}: Bool\n", quadrant_trust_var(quadrant)));
    }
    for quadrant in Quadrant::ALL {
        spec.push_str(&format!("out {}: Bool\n", dist_constraint_name(quadrant)));
    }
    spec.push('\n');

    for robot_index in 0..config.robots {
        for quadrant in Quadrant::ALL {
            spec.push_str(&format!("aux {}\n", quadrant_var(robot_index, quadrant)));
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
    }
    spec.push('\n');

    for quadrant in Quadrant::ALL {
        spec.push_str(&format!(
            "{} = {}\n",
            quadrant_trust_var(quadrant),
            quadrant_trust_expr(config, quadrant, half_width, half_height)
        ));
    }
    spec.push('\n');

    for quadrant in Quadrant::ALL {
        spec.push_str(&format!(
            "{} = {}\n",
            dist_constraint_name(quadrant),
            distribution_constraint_expr(config, quadrant)
        ));
    }

    spec
}

fn quadrant_trust_expr(
    config: &SimulationConfig,
    quadrant: Quadrant,
    half_width: f32,
    half_height: f32,
) -> String {
    if config.robots == 0 {
        return "true".to_string();
    }

    (0..config.robots)
        .map(|robot_index| {
            let pose = pose_var(robot_index);
            format!(
                "(!{} || (abs({}.x) <= {:.3} && abs({}.y) <= {:.3}))",
                quadrant_var(robot_index, quadrant),
                pose,
                half_width,
                pose,
                half_height
            )
        })
        .collect::<Vec<_>>()
        .join(" && ")
}

fn distribution_constraint_expr(config: &SimulationConfig, quadrant: Quadrant) -> String {
    let trust_var = quadrant_trust_var(quadrant);
    let mut expr = format!("monitored_at({}, \"None\")", trust_var);
    for candidate in (0..config.robots).rev() {
        expr = format!(
            "if {} then monitored_at({}, \"{}\") else {}",
            quadrant_var(candidate, quadrant),
            trust_var,
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

fn generate_output_map() -> String {
    let entries = Quadrant::ALL
        .iter()
        .map(|quadrant| {
            format!(
                "  \"{}\": {{ \"topic\": \"/quadrants/{}/trustworthy\", \"msg_type\": \"Bool\" }}",
                quadrant_trust_var(*quadrant),
                quadrant.topic_name()
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
        for quadrant in Quadrant::ALL {
            var_names.push(quadrant_var(robot_index, quadrant));
        }
    }
    for quadrant in Quadrant::ALL {
        var_names.push(quadrant_trust_var(quadrant));
        var_names.push(dist_constraint_name(quadrant));
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

    fn var_prefix(self) -> &'static str {
        match self {
            Quadrant::Ne => "ne",
            Quadrant::Nw => "nw",
            Quadrant::Sw => "sw",
            Quadrant::Se => "se",
        }
    }

    fn topic_name(self) -> &'static str {
        match self {
            Quadrant::Ne => "ne",
            Quadrant::Nw => "nw",
            Quadrant::Sw => "sw",
            Quadrant::Se => "se",
        }
    }
}

fn node_name(robot_index: usize) -> String {
    format!("R{}", robot_index + 1)
}

fn pose_var(robot_index: usize) -> String {
    format!("{}Pose", var_prefix(robot_index))
}

fn quadrant_trust_var(quadrant: Quadrant) -> String {
    format!("{}Trustworthy", quadrant.var_prefix())
}

fn dist_constraint_name(quadrant: Quadrant) -> String {
    format!("dist{}", quadrant.suffix())
}

fn quadrant_var(robot_index: usize, quadrant: Quadrant) -> String {
    format!("{}In{}", var_prefix(robot_index), quadrant.suffix())
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
            arena_width: 12.0,
            arena_height: 12.0,
            brownian_scale: 0.4,
            sim_hz: 60.0,
            publish_rate_hz: 10.0,
            robot_radius: 0.12,
            robot_labels: false,
            wall_avoidance_margin: 1.0,
            wall_avoidance_strength: 2.0,
            render_scale: 60.0,
            trustworthiness_checker_reconf_topic: "reconfig".to_string(),
        }
    }

    #[test]
    fn generated_spec_uses_four_quadrant_properties() {
        let spec = generate_spec(&config(3));

        for var in [
            "neTrustworthy",
            "nwTrustworthy",
            "swTrustworthy",
            "seTrustworthy",
        ] {
            assert!(spec.contains(&format!("out {var}: Bool")));
        }
        for constraint in ["distNE", "distNW", "distSW", "distSE"] {
            assert!(spec.contains(&format!("out {constraint}: Bool")));
        }

        assert!(!spec.contains("out r1Trustworthy: Bool"));
        assert!(!spec.contains("out dist1: Bool"));
    }

    #[test]
    fn quadrant_distribution_constraint_targets_matching_quadrant_nodes() {
        let spec = generate_spec(&config(2));

        assert!(spec.contains(
            "distNE = if r1InNE then monitored_at(neTrustworthy, \"R1\") else if r2InNE then monitored_at(neTrustworthy, \"R2\") else monitored_at(neTrustworthy, \"None\")"
        ));
        assert!(spec.contains(
            "distSW = if r1InSW then monitored_at(swTrustworthy, \"R1\") else if r2InSW then monitored_at(swTrustworthy, \"R2\") else monitored_at(swTrustworthy, \"None\")"
        ));
    }
}
