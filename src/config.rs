use clap::Parser;
use std::path::PathBuf;

#[derive(Clone, Debug, Parser)]
#[command(author, version, about)]
pub struct Args {
    #[arg(long, default_value_t = 10, value_parser = positive_usize)]
    pub robots: usize,

    #[arg(long, default_value_t = 42)]
    pub seed: u64,

    #[arg(long, default_value_t = -9.0)]
    pub arena_min_x: f32,

    #[arg(long, default_value_t = -11.0)]
    pub arena_min_y: f32,

    #[arg(long, default_value_t = 17.5, value_parser = positive_f32)]
    pub arena_width: f32,

    #[arg(long, default_value_t = 19.0, value_parser = positive_f32)]
    pub arena_height: f32,

    #[arg(long, default_value_t = 1.25, value_parser = non_negative_f32)]
    pub brownian_scale: f32,

    #[arg(long, default_value_t = 60.0, value_parser = positive_f32)]
    pub sim_hz: f32,

    #[arg(long, default_value_t = 2.0, value_parser = positive_f32)]
    pub publish_rate_hz: f32,

    #[arg(long, default_value_t = 0.12, value_parser = positive_f32)]
    pub robot_radius: f32,

    #[arg(long)]
    pub robot_labels: bool,

    #[arg(long, default_value_t = 1.5, value_parser = positive_f32)]
    pub wall_avoidance_margin: f32,

    #[arg(long, default_value_t = 2.5, value_parser = non_negative_f32)]
    pub wall_avoidance_strength: f32,

    #[arg(long)]
    pub no_ros: bool,

    #[arg(long = "trustworthiness-checker", visible_alias = "tc")]
    pub trustworthiness_checker: bool,

    #[arg(
        long = "trustworthiness-checker-dir",
        default_value = "../robosapiens-trustworthiness-checker"
    )]
    pub trustworthiness_checker_dir: PathBuf,

    #[arg(long = "trustworthiness-checker-profile", default_value = "dev-fast")]
    pub trustworthiness_checker_profile: String,

    #[arg(
        long = "trustworthiness-checker-work-dir",
        default_value = "target/trustworthiness-checker"
    )]
    pub trustworthiness_checker_work_dir: PathBuf,

    #[arg(
        long = "trustworthiness-checker-reconf-topic",
        default_value = "reconfig"
    )]
    pub trustworthiness_checker_reconf_topic: String,

    #[arg(
        long = "trustworthiness-checker-dist-graph-topic",
        default_value = "/dist_graph"
    )]
    pub trustworthiness_checker_dist_graph_topic: String,

    #[arg(
        long = "trustworthiness-checker-ros-setup",
        default_value = "../robosapiens-trustworthiness-checker/ros_interfaces/install/local_setup.bash"
    )]
    pub trustworthiness_checker_ros_setup: PathBuf,

    #[arg(long = "trustworthiness-checker-rust-log", default_value = "warn")]
    pub trustworthiness_checker_rust_log: String,
}

fn positive_f32(value: &str) -> Result<f32, String> {
    let value = value
        .parse::<f32>()
        .map_err(|err| format!("expected a number: {err}"))?;
    if value > 0.0 {
        Ok(value)
    } else {
        Err("expected a positive value".to_string())
    }
}

fn positive_usize(value: &str) -> Result<usize, String> {
    let value = value
        .parse::<usize>()
        .map_err(|err| format!("expected an integer: {err}"))?;
    if value > 0 {
        Ok(value)
    } else {
        Err("expected a positive integer".to_string())
    }
}

fn non_negative_f32(value: &str) -> Result<f32, String> {
    let value = value
        .parse::<f32>()
        .map_err(|err| format!("expected a number: {err}"))?;
    if value >= 0.0 {
        Ok(value)
    } else {
        Err("expected a non-negative value".to_string())
    }
}
