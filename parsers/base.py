"""赛道计时应用 - CSV 解析器基类接口"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseParser(ABC):
    """计时设备 CSV 解析器的抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """人类可读的解析器名称"""

    @property
    @abstractmethod
    def description(self) -> str:
        """解析器所处理格式的描述"""

    @abstractmethod
    def parse(self, **kwargs) -> Dict[str, Any]:
        """解析 CSV 文件并返回结构化阶段数据

        接收关键字参数传入文件路径，具体实现定义接受哪些文件
        （如 sector_path=, classification_path= 等）

        返回字典：
            session_name: str - 阶段名称
            session_type: str - 阶段类型（Practice/Qualifying/Race 等）
            laps: list[dict] - 圈速列表，每个字典包含：
                car_number, driver_name, category, lap_number,
                lap_time, sector_1/2/3, gap, speed, position,
                out_lap, in_lap, time_of_day, session_time,
                speed_trap_1/2/3/4
            standings: list[dict] - 成绩列表，每个字典包含：
                position, car_number, team_name, class_name, nationality,
                total_time, gap, diff, laps_completed, fastest_lap,
                fastest_lap_no, fastest_lap_speed, pit_stops, is_classified
        """

    @abstractmethod
    def detect(self, filepath: str) -> bool:
        """快速检测 CSV 是否匹配本解析器格式"""
