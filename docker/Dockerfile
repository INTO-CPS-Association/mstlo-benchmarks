ARG ROS_DISTRO=jazzy
# The published ROS-base image is pinned by its multi-architecture manifest digest.
# The osrf/ros mirror currently publishes Jazzy desktop/simulation tags only.
ARG ROS_BASE_DIGEST=sha256:da725acf8b0f9f30c683e33ffbdcd6482d077af96d6fdc7688c5f4f280b7d923
ARG RUST_VERSION=1.88.0
ARG UV_VERSION=0.8.14
ARG IMAGE_VERSION=dev
ARG REPOSITORY_REVISION=unknown
ARG PROFILE=bench-fast

FROM ros:${ROS_DISTRO}-ros-base@${ROS_BASE_DIGEST} AS build

ARG ROS_DISTRO
ARG RUST_VERSION
ARG UV_VERSION
ARG PROFILE
ENV ROS_DISTRO=${ROS_DISTRO} \
    RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH=/usr/local/cargo/bin:${PATH} \
    RUSTUP_TOOLCHAIN=${RUST_VERSION} \
    RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
    ROS_LOCALHOST_ONLY=1 \
    IDL_PACKAGE_FILTER=std_msgs\;geometry_msgs\;nav_msgs\;id_pose_msgs\;robo_sapiens_interfaces \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    cmake \
    curl \
    git \
    libclang-dev \
    libssl-dev \
    pkg-config \
    python3-colcon-common-extensions \
    python3-pip \
    python3-venv \
    ros-${ROS_DISTRO}-ament-cmake \
    ros-${ROS_DISTRO}-builtin-interfaces \
    ros-${ROS_DISTRO}-geometry-msgs \
    ros-${ROS_DISTRO}-nav-msgs \
    ros-${ROS_DISTRO}-rclcpp \
    ros-${ROS_DISTRO}-rmw-fastrtps-cpp \
    ros-${ROS_DISTRO}-rosidl-default-generators \
    ros-${ROS_DISTRO}-rosidl-default-runtime \
    ros-${ROS_DISTRO}-std-msgs \
    && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --profile minimal --default-toolchain "${RUST_VERSION}" \
    && rustc --version \
    && cargo --version

RUN python3 -m pip install --no-cache-dir --break-system-packages "uv==${UV_VERSION}" \
    && uv --version

WORKDIR /src

# Copy only files needed by Cargo and colcon before the expensive Rust build.
# Configurations, tests, and the runtime entrypoint are copied after this layer so
# changing a suite or shell wrapper does not invalidate the compiled artifacts.
COPY benchmark-runner/Cargo.toml benchmark-runner/Cargo.lock /src/benchmark-runner/
COPY benchmark-runner/src /src/benchmark-runner/src
COPY robosapiens-trustworthiness-checker/Cargo.toml \
    robosapiens-trustworthiness-checker/Cargo.lock \
    robosapiens-trustworthiness-checker/LICENSE.md \
    robosapiens-trustworthiness-checker/build.rs \
    /src/robosapiens-trustworthiness-checker/
COPY robosapiens-trustworthiness-checker/src /src/robosapiens-trustworthiness-checker/src
COPY robosapiens-trustworthiness-checker/libs /src/robosapiens-trustworthiness-checker/libs
COPY robosapiens-trustworthiness-checker/integrations/python \
    /src/robosapiens-trustworthiness-checker/integrations/python
COPY robosapiens-trustworthiness-checker/benches \
    /src/robosapiens-trustworthiness-checker/benches
COPY robosapiens-trustworthiness-checker/docs/src/assets/dataflow \
    /src/robosapiens-trustworthiness-checker/docs/src/assets/dataflow
COPY robosapiens-trustworthiness-checker/ros_interfaces \
    /src/robosapiens-trustworthiness-checker/ros_interfaces

RUN source /opt/ros/${ROS_DISTRO}/setup.bash \
    && cd /src/robosapiens-trustworthiness-checker/ros_interfaces \
    && colcon build --packages-select robo_sapiens_interfaces id_pose_msgs --merge-install

RUN source /opt/ros/${ROS_DISTRO}/setup.bash \
    && source /src/robosapiens-trustworthiness-checker/ros_interfaces/install/setup.bash \
    && cd /src/robosapiens-trustworthiness-checker \
    && cargo build --locked --profile "${PROFILE}" --features ros --bin trustworthiness_checker \
    && cd /src/benchmark-runner \
    && cargo build --locked --profile "${PROFILE}" --features ros

# Keep Python changes and suite edits out of the expensive Rust build cache.
COPY pyproject.toml uv.lock ./
COPY mstlo_bench ./mstlo_bench
RUN UV_PROJECT_ENVIRONMENT=/opt/venv uv sync --frozen --extra dev --no-editable

COPY configs /src/configs
COPY tests /src/tests

FROM ros:${ROS_DISTRO}-ros-base@${ROS_BASE_DIGEST} AS runtime

ARG ROS_DISTRO
ARG ROS_BASE_DIGEST
ARG IMAGE_VERSION
ARG REPOSITORY_REVISION
ENV ROS_DISTRO=${ROS_DISTRO} \
    PATH=/opt/venv/bin:/usr/local/bin:${PATH} \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib \
    ROS_LOCALHOST_ONLY=1 \
    RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
    IDL_PACKAGE_FILTER=std_msgs\;geometry_msgs\;nav_msgs\;id_pose_msgs\;robo_sapiens_interfaces \
    ROS_LOG_DIR=/tmp/mstlo-bench-ros \
    MSTLO_BENCH_ROOT=/opt/mstlo-bench \
    MSTLO_BENCH_RESULTS_ROOT=/results \
    MSTLO_BENCH_TESTS_DIR=/opt/mstlo-bench/tests \
    MSTLO_BENCH_PREBUILT=1 \
    MSTLO_RUNNER_BIN=/usr/local/bin/mstlo-benchmark-runner \
    MSTLO_CHECKER_BIN=/usr/local/bin/trustworthiness_checker \
    MSTLO_CHECKER_DIR=/opt/mstlo-bench \
    MSTLO_RUNNER_DIR=/opt/mstlo-bench \
    MSTLO_ROS_OVERLAY=/opt/ros_interfaces/install \
    MSTLO_BENCH_IMAGE_VERSION=${IMAGE_VERSION} \
    MSTLO_BENCH_REPOSITORY_REVISION=${REPOSITORY_REVISION} \
    HOME=/tmp
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
    fontconfig \
    libfreetype6 \
    libgcc-s1 \
    libssl3 \
    libstdc++6 \
    ros-${ROS_DISTRO}-builtin-interfaces \
    ros-${ROS_DISTRO}-geometry-msgs \
    ros-${ROS_DISTRO}-nav-msgs \
    ros-${ROS_DISTRO}-rclcpp \
    ros-${ROS_DISTRO}-rmw-fastrtps-cpp \
    ros-${ROS_DISTRO}-rosidl-default-runtime \
    ros-${ROS_DISTRO}-std-msgs \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/venv /opt/venv
COPY --from=build /src/robosapiens-trustworthiness-checker/ros_interfaces/install /opt/ros_interfaces/install
COPY --from=build /src/benchmark-runner/target/bench-fast/mstlo-benchmark-runner /usr/local/bin/mstlo-benchmark-runner
COPY --from=build /src/robosapiens-trustworthiness-checker/target/bench-fast/trustworthiness_checker /usr/local/bin/trustworthiness_checker
COPY --from=build /src/configs /opt/mstlo-bench/configs
COPY --from=build /src/tests /opt/mstlo-bench/tests
COPY docker/entrypoint.sh /usr/local/bin/mstlo-bench-entrypoint

RUN chmod 0755 /usr/local/bin/mstlo-bench-entrypoint \
    /usr/local/bin/mstlo-benchmark-runner \
    /usr/local/bin/trustworthiness_checker \
    && mkdir -p /opt/mstlo-bench /results /tmp/matplotlib /tmp/mstlo-bench-ros \
    && chown -R 1000:1000 /opt/venv /opt/mstlo-bench /results /tmp/matplotlib /tmp/mstlo-bench-ros

LABEL org.opencontainers.image.title="MSTLO reference benchmark" \
      org.opencontainers.image.version="${IMAGE_VERSION}" \
      org.opencontainers.image.revision="${REPOSITORY_REVISION}" \
      org.opencontainers.image.description="Prebuilt Docker execution environment for MSTLO latency benchmarks"

WORKDIR /opt/mstlo-bench
USER 1000:1000
ENTRYPOINT ["/usr/local/bin/mstlo-bench-entrypoint"]
CMD ["--help"]
