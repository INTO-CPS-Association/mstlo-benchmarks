# Latency report

## Series coverage

| semantics | property_set | transport | status | complete_robot_counts | planned_robot_counts |
| --- | --- | --- | --- | --- | --- |
| delayed-qualitative | confined | direct | complete | 6 | 6 |
| delayed-qualitative | confined | ros | complete | 6 | 6 |
| delayed-qualitative | dwell | direct | complete | 6 | 6 |
| delayed-qualitative | dwell | ros | complete | 6 | 6 |
| delayed-qualitative | occupancy | direct | complete | 6 | 6 |
| delayed-qualitative | occupancy | ros | complete | 6 | 6 |
| delayed-quantitative | confined | direct | complete | 6 | 6 |
| delayed-quantitative | confined | ros | complete | 6 | 6 |
| delayed-quantitative | dwell | direct | complete | 6 | 6 |
| delayed-quantitative | dwell | ros | complete | 6 | 6 |
| delayed-quantitative | occupancy | direct | complete | 6 | 6 |
| delayed-quantitative | occupancy | ros | complete | 6 | 6 |
| eager-qualitative | confined | direct | complete | 6 | 6 |
| eager-qualitative | confined | ros | complete | 6 | 6 |
| eager-qualitative | dwell | direct | complete | 6 | 6 |
| eager-qualitative | dwell | ros | complete | 6 | 6 |
| eager-qualitative | occupancy | direct | complete | 6 | 6 |
| eager-qualitative | occupancy | ros | complete | 6 | 6 |
| robustness-interval | confined | direct | complete | 6 | 6 |
| robustness-interval | confined | ros | complete | 6 | 6 |
| robustness-interval | dwell | direct | complete | 6 | 6 |
| robustness-interval | dwell | ros | partial | 4 | 6 |
| robustness-interval | occupancy | direct | complete | 6 | 6 |
| robustness-interval | occupancy | ros | complete | 6 | 6 |

Only robot counts with every configured seed are plotted; incomplete points are left blank.

## Per-robot results

| semantics | property_set | transport | robots | runs | expected_runs | complete | latency_samples_mean | latency_overhead_ms_p50_mean | latency_overhead_ms_p95_mean | latency_overhead_ms_p99_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| delayed-qualitative | confined | direct | 1 | 2 | 2 | True | 400 | 0.02797 | 0.04314 | 0.06172 |
| delayed-qualitative | confined | direct | 5 | 2 | 2 | True | 2000 | 0.04832 | 0.07993 | 0.1331 |
| delayed-qualitative | confined | direct | 10 | 2 | 2 | True | 4000 | 0.06723 | 0.09445 | 0.1374 |
| delayed-qualitative | confined | direct | 20 | 2 | 2 | True | 8000 | 0.1015 | 0.1548 | 0.2104 |
| delayed-qualitative | confined | direct | 50 | 2 | 2 | True | 2e+04 | 0.2046 | 0.2768 | 0.3587 |
| delayed-qualitative | confined | direct | 100 | 2 | 2 | True | 4e+04 | 0.3548 | 0.4818 | 0.5666 |
| delayed-qualitative | confined | ros | 1 | 2 | 2 | True | 400 | 1.567 | 26.24 | 26.41 |
| delayed-qualitative | confined | ros | 5 | 2 | 2 | True | 2000 | 22.11 | 22.25 | 22.41 |
| delayed-qualitative | confined | ros | 10 | 2 | 2 | True | 4000 | 41.37 | 41.54 | 41.79 |
| delayed-qualitative | confined | ros | 20 | 2 | 2 | True | 8000 | 43.85 | 43.97 | 44.05 |
| delayed-qualitative | confined | ros | 50 | 2 | 2 | True | 2e+04 | 43.37 | 43.62 | 44.06 |
| delayed-qualitative | confined | ros | 100 | 2 | 2 | True | 4e+04 | 27.02 | 27.44 | 27.74 |
| delayed-qualitative | dwell | direct | 1 | 2 | 2 | True | 100 | 0.06645 | 0.3323 | 0.3865 |
| delayed-qualitative | dwell | direct | 5 | 2 | 2 | True | 500 | 0.1253 | 0.4193 | 0.4909 |
| delayed-qualitative | dwell | direct | 10 | 2 | 2 | True | 1000 | 0.1124 | 0.446 | 0.5781 |
| delayed-qualitative | dwell | direct | 20 | 2 | 2 | True | 2000 | 0.1618 | 0.4857 | 0.5381 |
| delayed-qualitative | dwell | direct | 50 | 2 | 2 | True | 5000 | 0.344 | 0.6648 | 0.8208 |
| delayed-qualitative | dwell | direct | 100 | 2 | 2 | True | 1e+04 | 0.6345 | 1.012 | 1.106 |
| delayed-qualitative | dwell | ros | 1 | 2 | 2 | True | 100 | 46.53 | 46.72 | 46.86 |
| delayed-qualitative | dwell | ros | 5 | 2 | 2 | True | 500 | 25.91 | 26.08 | 26.28 |
| delayed-qualitative | dwell | ros | 10 | 2 | 2 | True | 1000 | 48.66 | 48.82 | 49.17 |
| delayed-qualitative | dwell | ros | 20 | 2 | 2 | True | 2000 | 25.37 | 25.48 | 25.57 |
| delayed-qualitative | dwell | ros | 50 | 2 | 2 | True | 5000 | 38.27 | 38.67 | 39.03 |
| delayed-qualitative | dwell | ros | 100 | 2 | 2 | True | 1e+04 | 31.74 | 32.32 | 32.78 |
| delayed-qualitative | occupancy | direct | 1 | 2 | 2 | True | 200 | 0.04287 | 0.297 | 0.3389 |
| delayed-qualitative | occupancy | direct | 5 | 2 | 2 | True | 200 | 0.1133 | 0.3731 | 0.5243 |
| delayed-qualitative | occupancy | direct | 10 | 2 | 2 | True | 200 | 0.1176 | 0.4003 | 0.4692 |
| delayed-qualitative | occupancy | direct | 20 | 2 | 2 | True | 200 | 0.1247 | 0.3972 | 0.4862 |
| delayed-qualitative | occupancy | direct | 50 | 2 | 2 | True | 200 | 0.4732 | 0.7588 | 0.8696 |
| delayed-qualitative | occupancy | direct | 100 | 2 | 2 | True | 200 | 1.597 | 2.046 | 2.328 |
| delayed-qualitative | occupancy | ros | 1 | 2 | 2 | True | 200 | 46.74 | 46.95 | 47.14 |
| delayed-qualitative | occupancy | ros | 5 | 2 | 2 | True | 200 | 25.5 | 25.67 | 25.93 |
| delayed-qualitative | occupancy | ros | 10 | 2 | 2 | True | 200 | 24.63 | 24.79 | 25.21 |
| delayed-qualitative | occupancy | ros | 20 | 2 | 2 | True | 200 | 45.1 | 45.28 | 45.68 |
| delayed-qualitative | occupancy | ros | 50 | 2 | 2 | True | 200 | 46.78 | 46.98 | 47.44 |
| delayed-qualitative | occupancy | ros | 100 | 2 | 2 | True | 200 | 44.71 | 45.14 | 45.6 |
| delayed-quantitative | confined | direct | 1 | 2 | 2 | True | 400 | 0.02776 | 0.04435 | 0.0514 |
| delayed-quantitative | confined | direct | 5 | 2 | 2 | True | 2000 | 0.04835 | 0.07123 | 0.0827 |
| delayed-quantitative | confined | direct | 10 | 2 | 2 | True | 4000 | 0.06785 | 0.09451 | 0.1089 |
| delayed-quantitative | confined | direct | 20 | 2 | 2 | True | 8000 | 0.1132 | 0.1587 | 0.1761 |
| delayed-quantitative | confined | direct | 50 | 2 | 2 | True | 2e+04 | 0.2088 | 0.2839 | 0.3675 |
| delayed-quantitative | confined | direct | 100 | 2 | 2 | True | 4e+04 | 0.3596 | 0.4928 | 0.5818 |
| delayed-quantitative | confined | ros | 1 | 2 | 2 | True | 400 | 47.71 | 47.86 | 48.05 |
| delayed-quantitative | confined | ros | 5 | 2 | 2 | True | 2000 | 47.02 | 47.16 | 47.46 |
| delayed-quantitative | confined | ros | 10 | 2 | 2 | True | 4000 | 23.79 | 23.92 | 24 |
| delayed-quantitative | confined | ros | 20 | 2 | 2 | True | 8000 | 45.11 | 45.28 | 45.57 |
| delayed-quantitative | confined | ros | 50 | 2 | 2 | True | 2e+04 | 42.8 | 43.07 | 43.5 |
| delayed-quantitative | confined | ros | 100 | 2 | 2 | True | 4e+04 | 38.64 | 39.12 | 39.74 |
| delayed-quantitative | dwell | direct | 1 | 2 | 2 | True | 100 | 0.02525 | 0.283 | 0.3155 |
| delayed-quantitative | dwell | direct | 5 | 2 | 2 | True | 500 | 0.1113 | 0.3416 | 1.096 |
| delayed-quantitative | dwell | direct | 10 | 2 | 2 | True | 1000 | 0.1224 | 0.3628 | 0.4721 |
| delayed-quantitative | dwell | direct | 20 | 2 | 2 | True | 2000 | 0.178 | 0.4849 | 0.5991 |
| delayed-quantitative | dwell | direct | 50 | 2 | 2 | True | 5000 | 0.4391 | 0.736 | 0.8867 |
| delayed-quantitative | dwell | direct | 100 | 2 | 2 | True | 1e+04 | 0.6417 | 1.047 | 1.256 |
| delayed-quantitative | dwell | ros | 1 | 2 | 2 | True | 100 | 25.41 | 25.6 | 25.78 |
| delayed-quantitative | dwell | ros | 5 | 2 | 2 | True | 500 | 44.49 | 44.8 | 45.05 |
| delayed-quantitative | dwell | ros | 10 | 2 | 2 | True | 1000 | 46.07 | 46.19 | 46.37 |
| delayed-quantitative | dwell | ros | 20 | 2 | 2 | True | 2000 | 44.57 | 44.71 | 44.78 |
| delayed-quantitative | dwell | ros | 50 | 2 | 2 | True | 5000 | 44 | 44.29 | 44.75 |
| delayed-quantitative | dwell | ros | 100 | 2 | 2 | True | 1e+04 | 31.6 | 32.13 | 33.12 |
| delayed-quantitative | occupancy | direct | 1 | 2 | 2 | True | 200 | 0.03134 | 0.2969 | 0.4182 |
| delayed-quantitative | occupancy | direct | 5 | 2 | 2 | True | 200 | 0.06097 | 0.3666 | 0.454 |
| delayed-quantitative | occupancy | direct | 10 | 2 | 2 | True | 200 | 0.05617 | 0.3352 | 0.3859 |
| delayed-quantitative | occupancy | direct | 20 | 2 | 2 | True | 200 | 0.1105 | 0.4188 | 0.5802 |
| delayed-quantitative | occupancy | direct | 50 | 2 | 2 | True | 200 | 0.4426 | 0.8095 | 0.9248 |
| delayed-quantitative | occupancy | direct | 100 | 2 | 2 | True | 200 | 1.577 | 2.066 | 2.185 |
| delayed-quantitative | occupancy | ros | 1 | 2 | 2 | True | 200 | 23.43 | 23.58 | 23.76 |
| delayed-quantitative | occupancy | ros | 5 | 2 | 2 | True | 200 | 44.73 | 44.87 | 45.09 |
| delayed-quantitative | occupancy | ros | 10 | 2 | 2 | True | 200 | 44.3 | 44.42 | 44.5 |
| delayed-quantitative | occupancy | ros | 20 | 2 | 2 | True | 200 | 47.16 | 47.4 | 47.69 |
| delayed-quantitative | occupancy | ros | 50 | 2 | 2 | True | 200 | 50.46 | 50.82 | 51.24 |
| delayed-quantitative | occupancy | ros | 100 | 2 | 2 | True | 200 | 4.457 | 5.097 | 5.499 |
| eager-qualitative | confined | direct | 1 | 2 | 2 | True | 400 | 0.02898 | 0.04675 | 0.07012 |
| eager-qualitative | confined | direct | 5 | 2 | 2 | True | 2000 | 0.04844 | 0.07174 | 0.09262 |
| eager-qualitative | confined | direct | 10 | 2 | 2 | True | 4000 | 0.07093 | 0.113 | 0.1372 |
| eager-qualitative | confined | direct | 20 | 2 | 2 | True | 8000 | 0.1076 | 0.1459 | 0.2424 |
| eager-qualitative | confined | direct | 50 | 2 | 2 | True | 2e+04 | 0.2041 | 0.2789 | 0.3903 |
| eager-qualitative | confined | direct | 100 | 2 | 2 | True | 4e+04 | 0.3681 | 0.4748 | 0.5451 |
| eager-qualitative | confined | ros | 1 | 2 | 2 | True | 400 | 44.47 | 44.72 | 45.03 |
| eager-qualitative | confined | ros | 5 | 2 | 2 | True | 2000 | 44.85 | 44.97 | 45.16 |
| eager-qualitative | confined | ros | 10 | 2 | 2 | True | 4000 | 45.48 | 45.64 | 45.89 |
| eager-qualitative | confined | ros | 20 | 2 | 2 | True | 8000 | 44.62 | 44.76 | 45.05 |
| eager-qualitative | confined | ros | 50 | 2 | 2 | True | 2e+04 | 38.92 | 39.11 | 39.3 |
| eager-qualitative | confined | ros | 100 | 2 | 2 | True | 4e+04 | 35.94 | 36.43 | 36.91 |
| eager-qualitative | dwell | direct | 1 | 2 | 2 | True | 100 | 1e+04 | 1e+04 | 1e+04 |
| eager-qualitative | dwell | direct | 5 | 2 | 2 | True | 500 | 1.5e+04 | 1.5e+04 | 1.5e+04 |
| eager-qualitative | dwell | direct | 10 | 2 | 2 | True | 1000 | 1.5e+04 | 1.5e+04 | 1.5e+04 |
| eager-qualitative | dwell | direct | 20 | 2 | 2 | True | 2000 | 1.5e+04 | 1.5e+04 | 1.5e+04 |
| eager-qualitative | dwell | direct | 50 | 2 | 2 | True | 5000 | 1.5e+04 | 1.5e+04 | 1.5e+04 |
| eager-qualitative | dwell | direct | 100 | 2 | 2 | True | 1e+04 | 1.5e+04 | 1.5e+04 | 1.5e+04 |
| eager-qualitative | dwell | ros | 1 | 2 | 2 | True | 100 | 1.005e+04 | 1.005e+04 | 1.005e+04 |
| eager-qualitative | dwell | ros | 5 | 2 | 2 | True | 500 | 1.502e+04 | 1.502e+04 | 1.502e+04 |
| eager-qualitative | dwell | ros | 10 | 2 | 2 | True | 1000 | 1.504e+04 | 1.504e+04 | 1.504e+04 |
| eager-qualitative | dwell | ros | 20 | 2 | 2 | True | 2000 | 1.504e+04 | 1.504e+04 | 1.504e+04 |
| eager-qualitative | dwell | ros | 50 | 2 | 2 | True | 5000 | 1.504e+04 | 1.504e+04 | 1.504e+04 |
| eager-qualitative | dwell | ros | 100 | 2 | 2 | True | 1e+04 | 1.504e+04 | 1.504e+04 | 1.504e+04 |
| eager-qualitative | occupancy | direct | 1 | 2 | 2 | True | 200 | 6250 | 8500 | 8700 |
| eager-qualitative | occupancy | direct | 5 | 2 | 2 | True | 200 | 1775 | 5825 | 6225 |
| eager-qualitative | occupancy | direct | 10 | 2 | 2 | True | 200 | 1e+04 | 1e+04 | 1e+04 |
| eager-qualitative | occupancy | direct | 20 | 2 | 2 | True | 200 | 1e+04 | 1e+04 | 1e+04 |
| eager-qualitative | occupancy | direct | 50 | 2 | 2 | True | 200 | 1e+04 | 1e+04 | 1e+04 |
| eager-qualitative | occupancy | direct | 100 | 2 | 2 | True | 200 | 1e+04 | 1e+04 | 1e+04 |
| eager-qualitative | occupancy | ros | 1 | 2 | 2 | True | 200 | 6252 | 8502 | 8702 |
| eager-qualitative | occupancy | ros | 5 | 2 | 2 | True | 200 | 1801 | 5851 | 6251 |
| eager-qualitative | occupancy | ros | 10 | 2 | 2 | True | 200 | 1.005e+04 | 1.005e+04 | 1.005e+04 |
| eager-qualitative | occupancy | ros | 20 | 2 | 2 | True | 200 | 1.004e+04 | 1.004e+04 | 1.004e+04 |
| eager-qualitative | occupancy | ros | 50 | 2 | 2 | True | 200 | 1.002e+04 | 1.002e+04 | 1.002e+04 |
| eager-qualitative | occupancy | ros | 100 | 2 | 2 | True | 200 | 1.005e+04 | 1.005e+04 | 1.005e+04 |
| robustness-interval | confined | direct | 1 | 2 | 2 | True | 400 | 0.03003 | 0.04512 | 0.0597 |
| robustness-interval | confined | direct | 5 | 2 | 2 | True | 2000 | 0.05597 | 0.08542 | 0.1218 |
| robustness-interval | confined | direct | 10 | 2 | 2 | True | 4000 | 0.08199 | 0.1153 | 0.161 |
| robustness-interval | confined | direct | 20 | 2 | 2 | True | 8000 | 0.1303 | 0.1837 | 0.224 |
| robustness-interval | confined | direct | 50 | 2 | 2 | True | 2e+04 | 0.2671 | 0.3763 | 0.4645 |
| robustness-interval | confined | direct | 100 | 2 | 2 | True | 4e+04 | 0.4869 | 0.6432 | 0.7823 |
| robustness-interval | confined | ros | 1 | 2 | 2 | True | 400 | 25.65 | 25.84 | 26.12 |
| robustness-interval | confined | ros | 5 | 2 | 2 | True | 2000 | 46.95 | 47.09 | 47.22 |
| robustness-interval | confined | ros | 10 | 2 | 2 | True | 4000 | 44.31 | 44.47 | 44.73 |
| robustness-interval | confined | ros | 20 | 2 | 2 | True | 8000 | 46.2 | 46.45 | 46.67 |
| robustness-interval | confined | ros | 50 | 2 | 2 | True | 2e+04 | 38.69 | 39.34 | 39.77 |
| robustness-interval | confined | ros | 100 | 2 | 2 | True | 4e+04 | 29.73 | 30.93 | 31.61 |
| robustness-interval | dwell | direct | 1 | 2 | 2 | True | 400 | 0.5148 | 0.9681 | 1.09 |
| robustness-interval | dwell | direct | 5 | 2 | 2 | True | 2000 | 2.763 | 4.408 | 4.815 |
| robustness-interval | dwell | direct | 10 | 2 | 2 | True | 4000 | 4.298 | 6.353 | 6.749 |
| robustness-interval | dwell | direct | 20 | 2 | 2 | True | 8000 | 6.394 | 10.39 | 11.62 |
| robustness-interval | dwell | direct | 50 | 2 | 2 | True | 2e+04 | 14.01 | 24.37 | 25.47 |
| robustness-interval | dwell | direct | 100 | 2 | 2 | True | 4e+04 | 26.8 | 57.71 | 60.18 |
| robustness-interval | dwell | ros | 1 | 2 | 2 | True | 400 | 50.57 | 52.32 | 52.61 |
| robustness-interval | dwell | ros | 5 | 2 | 2 | True | 2000 | 57.76 | 69.87 | 78.52 |
| robustness-interval | dwell | ros | 10 | 2 | 2 | True | 4000 | 57.37 | 79.04 | 87.39 |
| robustness-interval | dwell | ros | 20 | 2 | 2 | True | 7560 | 70.89 | 1243 | 1310 |
| robustness-interval | occupancy | direct | 1 | 2 | 2 | True | 400 | 0.1897 | 0.2709 | 0.3212 |
| robustness-interval | occupancy | direct | 5 | 2 | 2 | True | 400 | 0.772 | 1.079 | 1.236 |
| robustness-interval | occupancy | direct | 10 | 2 | 2 | True | 400 | 1.526 | 1.904 | 2.077 |
| robustness-interval | occupancy | direct | 20 | 2 | 2 | True | 400 | 2.636 | 3.238 | 3.539 |
| robustness-interval | occupancy | direct | 50 | 2 | 2 | True | 400 | 4.607 | 5.512 | 5.933 |
| robustness-interval | occupancy | direct | 100 | 2 | 2 | True | 400 | 7.835 | 9.059 | 9.947 |
| robustness-interval | occupancy | ros | 1 | 2 | 2 | True | 400 | 50.51 | 50.97 | 51.82 |
| robustness-interval | occupancy | ros | 5 | 2 | 2 | True | 400 | 53.56 | 59.24 | 68.17 |
| robustness-interval | occupancy | ros | 10 | 2 | 2 | True | 400 | 59.52 | 67.76 | 74.78 |
| robustness-interval | occupancy | ros | 20 | 2 | 2 | True | 400 | 75.41 | 84.75 | 90.53 |
| robustness-interval | occupancy | ros | 50 | 2 | 2 | True | 398.5 | 885.3 | 1172 | 1252 |
| robustness-interval | occupancy | ros | 100 | 2 | 2 | True | 397 | 1872 | 2299 | 2336 |
