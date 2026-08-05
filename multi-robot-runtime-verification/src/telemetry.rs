use std::{
    fs::{self, File},
    io::{BufWriter, Write},
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

use serde::Serialize;
use serde_json::json;

#[derive(Debug)]
pub struct TelemetryWriter {
    path: PathBuf,
    writer: BufWriter<File>,
}

impl TelemetryWriter {
    pub fn create(output_dir: &Path) -> Result<Self, String> {
        fs::create_dir_all(output_dir).map_err(|err| {
            format!(
                "failed to create benchmark output directory {}: {err}",
                output_dir.display()
            )
        })?;
        let path = output_dir.join("telemetry_events.jsonl");
        let file = File::create(&path)
            .map_err(|err| format!("failed to create telemetry file {}: {err}", path.display()))?;
        Ok(Self {
            path,
            writer: BufWriter::new(file),
        })
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    pub fn emit<T: Serialize>(
        &mut self,
        run_id: &str,
        role: &str,
        event_type: &str,
        elapsed_secs: f64,
        payload: T,
    ) -> Result<(), String> {
        let event = json!({
            "ts_unix_ms": unix_time_ms(),
            "run_id": run_id,
            "role": role,
            "event_type": event_type,
            "elapsed_secs": elapsed_secs,
            "payload": payload,
        });
        serde_json::to_writer(&mut self.writer, &event)
            .map_err(|err| format!("failed to serialize telemetry event: {err}"))?;
        self.writer
            .write_all(b"\n")
            .map_err(|err| format!("failed to write telemetry event: {err}"))
    }

    pub fn flush(&mut self) -> Result<(), String> {
        self.writer.flush().map_err(|err| {
            format!(
                "failed to flush telemetry file {}: {err}",
                self.path.display()
            )
        })
    }
}

fn unix_time_ms() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use std::fs;

    use super::*;

    #[test]
    fn telemetry_writer_serializes_jsonl_events() {
        let dir = std::env::temp_dir().join(format!(
            "robot_brownian_sim_telemetry_test_{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&dir);

        let mut writer = TelemetryWriter::create(&dir).unwrap();
        writer
            .emit(
                "run-a",
                "simulator",
                "tick",
                1.5,
                json!({"tick": 42, "messages": 3}),
            )
            .unwrap();
        writer.flush().unwrap();

        let contents = fs::read_to_string(writer.path()).unwrap();
        let value: serde_json::Value = serde_json::from_str(contents.trim()).unwrap();
        assert_eq!(value["run_id"], "run-a");
        assert_eq!(value["role"], "simulator");
        assert_eq!(value["event_type"], "tick");
        assert_eq!(value["payload"]["tick"], 42);

        let _ = fs::remove_dir_all(&dir);
    }
}
