"""
房間（Room）資料模型
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from datetime import datetime
from enum import Enum
import uuid


class RoomParameterType(str, Enum):
    """房間參數類型枚舉"""
    STRING = "string"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    LONG = "long"
    FLOAT = "float"
    URI = "uri"
    COMPONENT = "component"
    STRING_ARRAY = "string_array"
    INTEGER_ARRAY = "integer_array"
    LONG_ARRAY = "long_array"
    FLOAT_ARRAY = "float_array"


class RoomParameter(BaseModel):
    """房間參數模型"""
    name: str = Field(..., min_length=1, description="參數名稱")
    value_type: RoomParameterType = Field(..., description="參數類型")
    is_global: bool = Field(default=True, description="是否為全域參數")
    
    # 全域值
    global_value: Any = Field(None, description="全域參數值")
    
    # 用於非全域參數：設備 ID -> 值 的映射
    device_values: Dict[str, Any] = Field(default_factory=dict, description="設備專屬值映射")
    
    @property
    def adb_flag(self) -> str:
        """獲取對應的 ADB 參數 flag"""
        flags = {
            RoomParameterType.STRING: "-es",        # ex: -es key "string value"
            RoomParameterType.BOOLEAN: "-ez",       # ex: -ez key true
            RoomParameterType.INTEGER: "-ei",       # ex: -ei key 123
            RoomParameterType.LONG: "-el",          # ex: -el key 1234567890123
            RoomParameterType.FLOAT: "-ef",         # ex: -ef key 1.23
            RoomParameterType.URI: "-eu",           # ex: -eu key "content://..."
            RoomParameterType.COMPONENT: "-ecn",    # ex: -ecn key component/name
            RoomParameterType.STRING_ARRAY: "-esa", # ex: -esa key "v1,v2,v3"
            RoomParameterType.INTEGER_ARRAY: "-eia",# ex: -eia key 1,2,3
            RoomParameterType.LONG_ARRAY: "-ela",   # ex: -ela key 124,1245
            RoomParameterType.FLOAT_ARRAY: "-efa",  # ex: -efa key 1.1,2.2
        }
        return flags.get(self.value_type, "-es")


    def to_transport(
        self,
        device_meta_map: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        序列化參數用於網路傳輸：device_values 由 dict 轉為 list[{device_id,value}]
        如果提供 device_meta_map，可附帶 device_num 等其他元數據。
        """
        data = self.model_dump()
        if self.device_values:
            device_list = []
            for dev_id, value in self.device_values.items():
                # 允許 value 已經是 dict，並帶有 rotation_value
                if isinstance(value, dict):
                    v = value.get('value')
                    rot = value.get('rotation_value')
                else:
                    v = value
                    rot = None

                device_entry = {
                    'device_id': dev_id,
                    'value': v,
                    'rotation_value': rot
                }

                if device_meta_map and dev_id in device_meta_map:
                    meta = device_meta_map[dev_id]
                    if meta.get('num') is not None:
                        device_entry['device_num'] = meta['num']

                device_list.append(device_entry)
            data['device_values'] = device_list
        else:
            data['device_values'] = []
        return data


class Room(BaseModel):
    """房間模型"""
    room_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = Field(..., min_length=1, max_length=50, description="房間名稱")
    description: Optional[str] = Field(None, max_length=200, description="房間說明")
    max_devices: int = Field(default=0, ge=0, description="最大設備數量（0=無限制）")
    device_ids: List[str] = Field(default_factory=list, description="房間內設備 ID 列表")
    
    # Socket Server 設定
    socket_ip: Optional[str] = Field(None, description="Socket Server IP 地址")
    socket_port: Optional[int] = Field(None, ge=1, le=65535, description="Socket Server 端口")
    saved_user_position_z: Optional[float] = Field(None, description="房間記憶的使用者位置 z 座標")
    
    # 房間參數
    parameters: List[RoomParameter] = Field(default_factory=list, description="房間啟動參數列表")
    
    # 時間戳
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    @property
    def device_count(self) -> int:
        """獲取房間內設備數量"""
        return len(self.device_ids)
    
    @property
    def is_full(self) -> bool:
        """檢查房間是否已滿"""
        if self.max_devices == 0:  # 無限制
            return False
        return len(self.device_ids) >= self.max_devices
    
    @property
    def display_name(self) -> str:
        """顯示名稱"""
        return f"🏠 {self.name}"
    
    @property
    def capacity_text(self) -> str:
        """容量文字"""
        if self.max_devices == 0:
            return f"{self.device_count}"
        else:
            return f"{self.device_count}/{self.max_devices}"
    
    def add_device(self, device_id: str) -> bool:
        """
        添加設備到房間
        
        Args:
            device_id: 設備 ID
        
        Returns:
            是否成功
        """
        # 檢查是否已存在
        if device_id in self.device_ids:
            return False
        
        # 檢查是否已滿
        if self.is_full:
            return False
        
        self.device_ids.append(device_id)
        self.updated_at = datetime.now()
        return True
    
    def remove_device(self, device_id: str) -> bool:
        """
        從房間移除設備
        
        Args:
            device_id: 設備 ID
        
        Returns:
            是否成功
        """
        if device_id in self.device_ids:
            self.device_ids.remove(device_id)
            self.updated_at = datetime.now()
            return True
        return False
    
    def has_device(self, device_id: str) -> bool:
        """
        檢查設備是否在房間內
        
        Args:
            device_id: 設備 ID
        
        Returns:
            是否在房間內
        """
        return device_id in self.device_ids
    
    def to_dict(self) -> dict:
        """轉換為字典（用於儲存）"""
        data = self.model_dump(exclude_none=False)
        # 轉換 datetime 為字串
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        if self.updated_at:
            data['updated_at'] = self.updated_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Room':
        """從字典創建（用於讀取）"""
        # 轉換字串為 datetime
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if 'updated_at' in data and isinstance(data['updated_at'], str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        return cls(**data)
