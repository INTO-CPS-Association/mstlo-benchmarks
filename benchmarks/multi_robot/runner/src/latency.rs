use std::{collections::BTreeMap, time::Instant};

use serde::Serialize;
use trustworthiness_checker::VarName;

const MISSING: i64 = i64::MIN;

#[derive(Clone, Copy)]
struct Publication {
    timestamp_ns: u64,
    elapsed_ns: u64,
}

pub struct LatencyTracker {
    started: Instant,
    finalization_horizon_ns: u64,
    latency_baseline_ns: u64,
    publications: Vec<Publication>,
    property_ids: BTreeMap<VarName, usize>,
    property_count: usize,
    latencies: Vec<i64>,
}

#[derive(Serialize)]
pub struct LatencySummary {
    pub latency_samples: u64,
    pub latency_expected_samples: u64,
    pub latency_complete: bool,
    pub latency_invalid_outputs: u64,
    pub latency_overhead_ms_p50: Option<f64>,
    pub latency_overhead_ms_p95: Option<f64>,
    pub latency_overhead_ms_p99: Option<f64>,
    pub result_latency_ms_p50: Option<f64>,
    pub result_latency_ms_p95: Option<f64>,
    pub result_latency_ms_p99: Option<f64>,
}

impl LatencySummary {
    /// Whether at least `minimum_percent` of the expected property/timestamp
    /// verdicts arrived. A run with no expected verdicts never qualifies.
    pub fn meets_completeness(&self, minimum_percent: u64) -> bool {
        self.latency_expected_samples > 0
            && self.latency_samples.saturating_mul(100)
                >= self
                    .latency_expected_samples
                    .saturating_mul(minimum_percent)
    }
}

impl LatencyTracker {
    pub fn new(
        finalization_horizon_ms: u64,
        latency_baseline_ms: u64,
        properties: impl IntoIterator<Item = VarName>,
    ) -> Self {
        let property_ids: BTreeMap<_, _> = properties
            .into_iter()
            .enumerate()
            .map(|(index, name)| (name, index))
            .collect();
        let property_count = property_ids.len();
        Self {
            started: Instant::now(),
            finalization_horizon_ns: finalization_horizon_ms.saturating_mul(1_000_000),
            latency_baseline_ns: latency_baseline_ms.saturating_mul(1_000_000),
            publications: Vec::new(),
            property_ids,
            property_count,
            latencies: Vec::new(),
        }
    }

    pub fn property_id(&self, name: &VarName) -> Option<usize> {
        self.property_ids.get(name).copied()
    }

    pub fn record_input(&mut self, timestamp_ns: u64) {
        if self
            .publications
            .last()
            .is_some_and(|entry| entry.timestamp_ns == timestamp_ns)
        {
            return;
        }
        self.publications.push(Publication {
            timestamp_ns,
            elapsed_ns: self.elapsed_ns(),
        });
    }

    pub fn record_output(&mut self, property_id: usize, timestamp_ns: u64) {
        let Ok(timestamp_index) = self
            .publications
            .binary_search_by_key(&timestamp_ns, |entry| entry.timestamp_ns)
        else {
            return;
        };
        let slot = timestamp_index * self.property_count + property_id;
        if self.latencies.len() <= slot {
            self.latencies.resize(slot + 1, MISSING);
        }
        if self.latencies[slot] != MISSING {
            return;
        }
        let published_ns = self.publications[timestamp_index].elapsed_ns;
        let elapsed_ns = self.elapsed_ns().saturating_sub(published_ns);
        self.latencies[slot] = elapsed_ns.try_into().unwrap_or(i64::MAX);
    }

    pub fn summary(&mut self, invalid_outputs: u64) -> LatencySummary {
        let expected_samples = self
            .expected_timestamp_count()
            .saturating_mul(self.property_count);
        self.latencies.truncate(expected_samples);
        self.latencies.retain(|value| *value != MISSING);
        self.latencies.sort_unstable();
        let samples = self.latencies.len() as u64;
        let expected_samples = expected_samples as u64;
        let percentile_ns = |fraction: f64| {
            if self.latencies.is_empty() {
                return None;
            }
            let index =
                ((self.latencies.len() as f64 * fraction) as usize).min(self.latencies.len() - 1);
            self.latencies[index].try_into().ok()
        };
        let result_latency_percentile = |fraction| {
            percentile_ns(fraction).map(|latency_ns: u64| latency_ns as f64 / 1_000_000.0)
        };
        let latency_overhead_percentile = |fraction| {
            percentile_ns(fraction).map(|latency_ns: u64| {
                latency_ns.saturating_sub(self.latency_baseline_ns) as f64 / 1_000_000.0
            })
        };
        LatencySummary {
            latency_samples: samples,
            latency_expected_samples: expected_samples,
            latency_complete: samples == expected_samples && expected_samples > 0,
            latency_invalid_outputs: invalid_outputs,
            latency_overhead_ms_p50: latency_overhead_percentile(0.50),
            latency_overhead_ms_p95: latency_overhead_percentile(0.95),
            latency_overhead_ms_p99: latency_overhead_percentile(0.99),
            result_latency_ms_p50: result_latency_percentile(0.50),
            result_latency_ms_p95: result_latency_percentile(0.95),
            result_latency_ms_p99: result_latency_percentile(0.99),
        }
    }

    fn expected_timestamp_count(&self) -> usize {
        let Some(last) = self.publications.last() else {
            return 0;
        };
        if last.timestamp_ns < self.finalization_horizon_ns {
            return 0;
        }
        let last_output_timestamp = last.timestamp_ns - self.finalization_horizon_ns;
        self.publications
            .partition_point(|entry| entry.timestamp_ns <= last_output_timestamp)
    }

    fn elapsed_ns(&self) -> u64 {
        self.started
            .elapsed()
            .as_nanos()
            .try_into()
            .unwrap_or(u64::MAX)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tracker_keeps_only_the_first_verdict_per_property_and_timestamp() {
        let property = VarName::new("p");
        let mut tracker = LatencyTracker::new(0, 0, [property.clone()]);
        tracker.record_input(0);
        let property_id = tracker.property_id(&property).unwrap();
        tracker.record_output(property_id, 0);
        tracker.record_output(property_id, 0);
        let summary = tracker.summary(0);
        assert_eq!(summary.latency_samples, 1);
        assert_eq!(summary.latency_expected_samples, 1);
        assert!(summary.latency_complete);
    }

    #[test]
    fn tracker_reports_result_latency_and_semantics_baseline_overhead() {
        let property = VarName::new("p");
        let mut tracker = LatencyTracker::new(1_000, 1_000, [property.clone()]);
        tracker.record_input(0);
        tracker.record_output(tracker.property_id(&property).unwrap(), 0);
        tracker.record_input(1_000_000_000);
        let summary = tracker.summary(0);
        assert_eq!(summary.latency_expected_samples, 1);
        assert!(summary.result_latency_ms_p50.unwrap() >= 0.0);
        assert_eq!(summary.latency_overhead_ms_p50, Some(0.0));
    }

    fn summary_with(samples: u64, expected_samples: u64) -> LatencySummary {
        LatencySummary {
            latency_samples: samples,
            latency_expected_samples: expected_samples,
            latency_complete: samples == expected_samples,
            latency_invalid_outputs: 0,
            latency_overhead_ms_p50: None,
            latency_overhead_ms_p95: None,
            latency_overhead_ms_p99: None,
            result_latency_ms_p50: None,
            result_latency_ms_p95: None,
            result_latency_ms_p99: None,
        }
    }

    #[test]
    fn summary_meets_completeness_at_the_threshold() {
        assert!(summary_with(18_000, 20_000).meets_completeness(90));
        assert!(summary_with(20_000, 20_000).meets_completeness(90));
    }

    #[test]
    fn summary_misses_completeness_below_the_threshold() {
        assert!(!summary_with(17_999, 20_000).meets_completeness(90));
        assert!(!summary_with(0, 20_000).meets_completeness(90));
    }

    #[test]
    fn summary_without_expected_verdicts_never_meets_completeness() {
        assert!(!summary_with(0, 0).meets_completeness(90));
    }

    #[test]
    fn tracker_payload_is_eight_bytes_per_property_timestamp() {
        assert_eq!(std::mem::size_of::<Publication>(), 16);
        assert_eq!(std::mem::size_of::<i64>(), 8);
    }
}
