try:
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
except Exception:
    rclpy = None
    Node = object
    SingleThreadedExecutor = None