#!/usr/bin/env bash
set -e

source /opt/ros/humble/setup.bash
source /home/baris-brew/BB3_ROS_WS/install/local_setup.bash

cd /home/baris-brew/Downloads/robot_self_teaching_tool
python3 main.py

