"""赛道计时应用 - 数据库模型定义"""

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone

# SQLAlchemy 数据库实例
db = SQLAlchemy()


class User(db.Model):
    """用户账号 - 用于登录认证"""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)       # 用户名
    password_hash = db.Column(db.String(256), nullable=False)              # 密码哈希
    is_admin = db.Column(db.Boolean, default=False)                        # 是否管理员
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))  # 创建时间

    def set_password(self, password: str):
        """设置密码（自动哈希）"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """校验密码"""
        return check_password_hash(self.password_hash, password)


class TimeKeeper(db.Model):
    """计时设备类型 - 对应不同的 CSV 解析器"""
    __tablename__ = "time_keepers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)          # 名称（如"Swiss Timing"）
    parser_module = db.Column(db.String(100), nullable=False)              # 解析器模块名
    description = db.Column(db.Text, default="")                           # 描述

    events = db.relationship("Event", back_populates="time_keeper")       # 关联的赛事


class Event(db.Model):
    """赛事 - 一次比赛活动，包含多个 Session"""
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)                       # 赛事名称
    track = db.Column(db.String(200), default="")                          # 赛道
    year = db.Column(db.Integer, nullable=True)                            # 年份
    championship = db.Column(db.String(200), default="")                   # 锦标赛
    event_date = db.Column(db.Date, nullable=True)                         # 比赛日期
    time_keeper_id = db.Column(db.Integer, db.ForeignKey("time_keepers.id"), nullable=True)  # 计时设备类型
    is_hidden = db.Column(db.Boolean, default=False)                       # 是否对非管理员隐藏
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))  # 创建时间

    time_keeper = db.relationship("TimeKeeper", back_populates="events")
    sessions = db.relationship(
        "Session",
        back_populates="event",
        order_by="Session.sort_order, Session.created_at",
        cascade="all, delete-orphan",
    )


class Session(db.Model):
    """阶段 - 赛事下的一个环节（如排位赛、正赛）"""
    __tablename__ = "sessions"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)  # 所属赛事
    name = db.Column(db.String(200), nullable=False)                       # 阶段名称
    session_type = db.Column(db.String(50), nullable=False)                # 类型（Practice/Qualifying/Race 等）
    start_time = db.Column(db.DateTime, nullable=True)                     # 开始时间
    sort_order = db.Column(db.Integer, nullable=False, default=0)          # 排序序号
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))  # 创建时间

    event = db.relationship("Event", back_populates="sessions")
    laps = db.relationship("LapRecord", back_populates="session",
                           order_by="LapRecord.lap_number", cascade="all, delete-orphan")
    standings = db.relationship("Standing", back_populates="session",
                                order_by="Standing.position", cascade="all, delete-orphan")


class Standing(db.Model):
    """成绩单 - 每辆车的最终排名结果"""
    __tablename__ = "standings"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)  # 所属阶段
    position = db.Column(db.Integer, nullable=False)                        # 名次
    car_number = db.Column(db.String(20), nullable=False)                   # 车号
    team_name = db.Column(db.String(200), default="")                       # 车队名称
    class_name = db.Column(db.String(100), default="")                      # 组别
    nationality = db.Column(db.String(10), default="")                      # 国籍
    total_time = db.Column(db.Float, nullable=True)                         # 总用时（秒）
    gap = db.Column(db.Float, nullable=True)                                # 与前车差距（秒）
    diff = db.Column(db.Float, nullable=True)                               # 与第一名差距（秒）
    laps_completed = db.Column(db.Integer, nullable=True)                   # 完成圈数
    fastest_lap = db.Column(db.Float, nullable=True)                        # 最快圈速
    fastest_lap_no = db.Column(db.Integer, nullable=True)                   # 最快圈所在圈数
    fastest_lap_speed = db.Column(db.Float, nullable=True)                  # 最快圈平均速度
    pit_stops = db.Column(db.Integer, default=0)                            # 进站次数
    is_classified = db.Column(db.Boolean, default=True)                     # 是否完赛
    car_model = db.Column(db.String(100), default="")                       # 车型
    series_color = db.Column(db.String(20), default="")                     # 按车号配色
    model_color = db.Column(db.String(20), default="")                      # 按车型配色
    gap_text = db.Column(db.String(50), default="")                         # 差距文本（如"+1.234"）
    diff_text = db.Column(db.String(50), default="")                        # 与第一名差距文本

    session = db.relationship("Session", back_populates="standings")


class CarConfig(db.Model):
    """车辆配置 - 每个赛事每辆车的显示配置"""
    __tablename__ = "car_configs"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)  # 所属赛事
    car_number = db.Column(db.String(20), nullable=False)                   # 车号
    car_model = db.Column(db.String(100), default="")                       # 车型
    series_color = db.Column(db.String(20), default="")                     # 按车号颜色
    model_color = db.Column(db.String(20), default="")                      # 按车型颜色
    team_name = db.Column(db.String(200), default="")                       # 车队名称
    class_name = db.Column(db.String(100), default="")                      # 组别

    event = db.relationship("Event", backref="car_configs")


class CarModelColor(db.Model):
    """全局车型→颜色映射 - 用于"按车型"图表模式"""
    __tablename__ = "car_model_colors"

    id = db.Column(db.Integer, primary_key=True)
    car_model = db.Column(db.String(100), unique=True, nullable=False)      # 车型名称
    model_color = db.Column(db.String(20), default="")                      # 对应颜色


class LapRecord(db.Model):
    """圈速记录 - 每辆车每一圈的数据"""
    __tablename__ = "lap_records"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)  # 所属阶段
    car_number = db.Column(db.String(20), nullable=False)                   # 车号
    driver_name = db.Column(db.String(200), default="")                     # 车手名称
    category = db.Column(db.String(100), default="")                        # 类别/组别
    lap_number = db.Column(db.Integer, nullable=False)                      # 圈数
    lap_time = db.Column(db.Float, nullable=True)                           # 圈速（秒）
    sector_1 = db.Column(db.Float, nullable=True)                           # S1 分段用时
    sector_2 = db.Column(db.Float, nullable=True)                           # S2 分段用时
    sector_3 = db.Column(db.Float, nullable=True)                           # S3 分段用时
    gap = db.Column(db.Float, nullable=True)                                # 与前车差距
    speed = db.Column(db.Float, nullable=True)                              # 平均速度（兼容旧字段）
    speed_trap_1 = db.Column(db.Float, nullable=True)                       # 测速点 1
    speed_trap_2 = db.Column(db.Float, nullable=True)                       # 测速点 2
    speed_trap_3 = db.Column(db.Float, nullable=True)                       # 测速点 3
    speed_trap_4 = db.Column(db.Float, nullable=True)                       # 测速点 4（极速）
    position = db.Column(db.Integer, nullable=True)                         # 当前名次
    is_best = db.Column(db.Boolean, default=False)                          # 是否该车最快圈
    out_lap = db.Column(db.Boolean, default=False)                          # 出站圈
    in_lap = db.Column(db.Boolean, default=False)                           # 进站圈
    track_limit = db.Column(db.Boolean, default=False)                      # 是否被判定赛道限制
    time_out_lap = db.Column(db.Float, nullable=True)                       # 出站时间戳
    time_in_lap = db.Column(db.Float, nullable=True)                        # 进站时间戳
    time_of_day = db.Column(db.String(20), default="")                      # 当日时间
    session_time = db.Column(db.Float, nullable=True)                       # 从阶段开始经过的时间（秒）
    car_model = db.Column(db.String(100), default="")                       # 车型
    series_color = db.Column(db.String(20), default="")                     # 按车号颜色
    model_color = db.Column(db.String(20), default="")                      # 按车型颜色

    session = db.relationship("Session", back_populates="laps")
