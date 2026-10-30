import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

@dataclass(init=False)
class SoundPad:
    filepath: Optional[str] = None
    hotkey: Optional[str] = None
    randomize: bool = False
    _volume: float = field(default=1.0, repr=False)

    def __init__(
        self,
        filepath: Optional[str] = None,
        hotkey: Optional[str] = None,
        volume: float = 1.0,
        randomize: bool = False,
    ):
        self.filepath = filepath
        self.hotkey = hotkey
        self.randomize = randomize
        self.volume = volume

    @property
    def volume(self) -> float:
        return self._volume

    @volume.setter
    def volume(self, value: float) -> None:
        self._volume = max(0.0, min(1.0, float(value)))

    def to_dict(self) -> dict:
        return {
            "filepath": self.filepath,
            "hotkey": self.hotkey,
            "volume": self.volume,
            "randomize": self.randomize,
        }

@dataclass
class SoundboardConfig:
    banks: List[List[SoundPad]] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.banks:
            self.banks = [[SoundPad() for _ in range(8)] for _ in range(1)]
            
    def save(self, path: Path):
        data = {"banks": [[pad.to_dict() for pad in bank] for bank in self.banks]}
        path.write_text(json.dumps(data, indent=2))
        
    @classmethod
    def load(cls, path: Path) -> "SoundboardConfig":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text())
            config = cls()
            config.banks = []
            for bank_data in data.get("banks", []):
                bank = []
                for pad_data in bank_data:
                    pad = SoundPad(
                        filepath=pad_data.get("filepath"),
                        hotkey=pad_data.get("hotkey"),
                        volume=max(0.0, min(1.0, pad_data.get("volume", 1.0))),
                        randomize=pad_data.get("randomize", False)
                    )
                    bank.append(pad)
                if len(bank) < 8:
                    bank.extend([SoundPad() for _ in range(8 - len(bank))])
                config.banks.append(bank[:8])
            if not config.banks:
                config.banks = [[SoundPad() for _ in range(8)] for _ in range(1)]
            return config
        except Exception:
            return cls()
