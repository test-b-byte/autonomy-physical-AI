"""
GHOST robot bringup (Jetson, inside the Isaac ROS environment).

  ros2 launch jetson/launch/robot.launch.py                  camera + cuVSLAM + Nav2
  ros2 launch jetson/launch/robot.launch.py nav2:=false      camera + cuVSLAM only (odometry bench test)
  ros2 launch jetson/launch/robot.launch.py color:=true      also stream colour (better person detection)
  ros2 launch jetson/launch/robot.launch.py cam_x:=0.12 cam_z:=0.10   camera mount offset (MEASURE)

Frames:  odom → camera_link (cuVSLAM)  →  base_link (static, from cam_x/cam_z)
         map → odom (static identity; there is no global map — GHOST's grid is
         anchored at the launch point, which is the odom origin)
Topics:  /visual_slam/tracking/odometry   pose for the GHOST bridge
         /camera/depth/points              obstacles for Nav2's costmaps
         /camera/left_ir/image_raw/compressed  frames for the Pi detector

Nav2 runs only the servers GHOST uses (planner, controller, behaviours,
navigator) under one lifecycle manager; params in jetson/config/nav2_params.yaml
(override with nav2_params:=/path/to/your.yaml).
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration as Cfg
from launch_ros.actions import ComposableNodeContainer, Node
from launch_ros.descriptions import ComposableNode

HERE = os.path.dirname(os.path.realpath(__file__))
DEFAULT_NAV2_PARAMS = os.path.join(HERE, "..", "config", "nav2_params.yaml")
NAV2_NODES = [
    ("nav2_planner", "planner_server"),
    ("nav2_controller", "controller_server"),
    ("nav2_behaviors", "behavior_server"),
    ("nav2_bt_navigator", "bt_navigator"),
]


def static_tf(parent, child, x="0", y="0", z="0", yaw="0"):
    return Node(package="tf2_ros", executable="static_transform_publisher",
                name=f"tf_{parent}_to_{child}",
                arguments=["--x", x, "--y", y, "--z", z, "--roll", "0", "--pitch", "0",
                           "--yaw", yaw, "--frame-id", parent, "--child-frame-id", child])


def generate_launch_description():
    args = [
        DeclareLaunchArgument("nav2", default_value="true"),
        DeclareLaunchArgument("color", default_value="false",
                              description="enable the colour stream (more USB bandwidth)"),
        DeclareLaunchArgument("cam_x", default_value="0.0",
                              description="m: camera ahead of base_link (robot centre)"),
        DeclareLaunchArgument("cam_z", default_value="0.0",
                              description="m: camera above base_link"),
        DeclareLaunchArgument("nav2_params", default_value=DEFAULT_NAV2_PARAMS),
    ]

    camera = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory("orbbec_camera"), "launch", "gemini_330_series.launch.py")),
        launch_arguments={
            "enable_left_ir": "true", "enable_right_ir": "true",
            "enable_laser": "false",            # IR projector off: cuVSLAM needs clean stereo
            "enable_depth": "true", "enable_point_cloud": "true",
            "enable_color": Cfg("color"),
        }.items())

    vslam = ComposableNodeContainer(
        name="ghost_vslam_container", namespace="", package="rclcpp_components",
        executable="component_container", output="screen",
        composable_node_descriptions=[ComposableNode(
            name="visual_slam_node", package="isaac_ros_cuvslam",
            plugin="nvidia::isaac_ros::visual_slam::VisualSlamNode",
            parameters=[{
                "num_cameras": 2,
                "rectified_images": True,
                "enable_image_denoising": False,
                "enable_localization_n_mapping": False,
                "base_frame": "camera_link",
                "odom_frame": "odom",
                "publish_odom_to_base_tf": True,
                "publish_map_to_odom_tf": False,     # we publish a static identity instead
                "image_qos": "SENSOR_DATA",
                "image_jitter_threshold_ms": 120.0,
            }],
            remappings=[
                ("visual_slam/image_0", "/camera/left_ir/image_raw"),
                ("visual_slam/camera_info_0", "/camera/left_ir/camera_info"),
                ("visual_slam/image_1", "/camera/right_ir/image_raw"),
                ("visual_slam/camera_info_1", "/camera/right_ir/camera_info"),
            ])])

    # base_link sits behind/below the camera: child pose in parent frame
    base_tf = Node(package="tf2_ros", executable="static_transform_publisher",
                   name="tf_camera_to_base",
                   arguments=["--x", ["-", Cfg("cam_x")], "--y", "0", "--z", ["-", Cfg("cam_z")],
                              "--roll", "0", "--pitch", "0", "--yaw", "0",
                              "--frame-id", "camera_link", "--child-frame-id", "base_link"])

    nav2_nodes = [Node(package=pkg, executable=exe, name=exe, output="screen",
                       parameters=[Cfg("nav2_params")])
                  for pkg, exe in NAV2_NODES]
    lifecycle = Node(package="nav2_lifecycle_manager", executable="lifecycle_manager",
                     name="lifecycle_manager_navigation", output="screen",
                     parameters=[{"autostart": True, "node_names": [e for _, e in NAV2_NODES],
                                  "bond_timeout": 8.0}])
    # Nav2 waits for odometry + TF from the camera stack before it starts
    nav2 = TimerAction(period=12.0, actions=[
        GroupAction(nav2_nodes + [lifecycle], condition=IfCondition(Cfg("nav2")))])

    return LaunchDescription(args + [
        camera, vslam, base_tf, static_tf("map", "odom"), nav2,
    ])
