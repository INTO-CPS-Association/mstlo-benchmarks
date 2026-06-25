#!/usr/bin/env python3
import argparse
import random

import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32, String

try:
    import yaml
except ImportError:
    yaml = None


class PropertiesPublisher(Node):
    def __init__(self, config_path, log_level):
        super().__init__("properties_publisher")
        self.publishers_ = {}
        self.log_level = log_level

        yaml_data = load_config(config_path)

        for entry in yaml_data:
            topic_name = entry["topic_name"]
            publisher = self.create_publisher_for(entry)
            self.publishers_[topic_name] = {
                "publisher": publisher,
                "value": entry["start_value"],
                "topic_type": entry["topic_type"],
                "modify": entry["modify"],
            }

        self.timer = self.create_timer(1.0, self.timer_callback)

    def create_publisher_for(self, yaml_entry):
        if yaml_entry["topic_type"] == "Int32":
            return self.create_publisher(Int32, yaml_entry["topic_name"], 10)
        return self.create_publisher(String, yaml_entry["topic_name"], 10)

    def timer_callback(self):
        for topic, publisher_data in self.publishers_.items():
            modify = publisher_data["modify"].split(" ")[0]
            if "Int" in publisher_data["topic_type"]:
                msg = Int32()
                msg.data = int(publisher_data["value"])
                if modify == "increment":
                    publisher_data["value"] += 1
                elif modify == "stoch_inc":
                    probability = float(publisher_data["modify"].split("stoch_inc")[1])
                    publisher_data["value"] = (
                        0
                        if random.random() < probability
                        else publisher_data["value"] + 1
                    )
                elif modify == "stoch_inc_dec":
                    probability = float(publisher_data["modify"].split("stoch_inc_dec")[1])
                    publisher_data["value"] += 1 if random.random() < probability else -1
            else:
                msg = String()
                msg.data = str(publisher_data["value"])

            publisher_data["publisher"].publish(msg)
            if self.log_level != "WARN":
                self.get_logger().info(f"Publishing: {msg.data} on topic {topic}")


def load_config(config_path):
    with open(config_path, "r", encoding="utf-8") as file:
        if yaml is not None:
            return yaml.safe_load(file)
        return parse_simple_yaml(file)


def parse_simple_yaml(lines):
    entries = []
    current = None
    for raw_line in lines:
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("- "):
            current = {}
            entries.append(current)
            line = line[2:].strip()
        if current is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        current[key.strip()] = parse_scalar(value.strip())
    return entries


def parse_scalar(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--log-level", default="WARN")
    parsed, ros_args = parser.parse_known_args(args)

    rclpy.init(args=ros_args)
    publisher = PropertiesPublisher(parsed.config, parsed.log_level)
    try:
        rclpy.spin(publisher)
    finally:
        publisher.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
