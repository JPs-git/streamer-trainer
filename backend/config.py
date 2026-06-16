import os
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv


class Config:
    def __init__(self, path: Optional[str] = None):
        env_path = Path(".env")
        if env_path.exists():
            load_dotenv(env_path)

        # Clear proxy env vars — httpx/openai SDK picks them up from environment
        # and WSL2's ~/.bashrc sets http_proxy to a non-running host proxy
        for key in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"]:
            os.environ.pop(key, None)

        if path is None:
            path = os.environ.get("CONFIG_PATH", "config.yaml")

        config_file = Path(path)
        if not config_file.is_file():
            default_path = Path("config.default.yaml")
            if default_path.is_file():
                import shutil
                shutil.copy(str(default_path), str(config_file))
            else:
                raise FileNotFoundError(
                    f"Config file not found at: {os.path.abspath(path)}. "
                    "Set CONFIG_PATH env var or ensure the file exists."
                )

        try:
            with open(config_file) as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Malformed YAML in config file '{path}': {e}")

        if raw is None:
            raise ValueError(f"Config file '{path}' is empty")

        try:
            server_conf = raw["server"]
            self.host = server_conf["host"]
            self.port = server_conf["port"]

            asr_conf = raw["asr"]
            self.asr_engine = asr_conf.get("engine", "onnx")
            self.asr_model_path = asr_conf.get("model_path", "")
            self.asr_tokens_path = asr_conf.get("tokens_path", "")
            self.asr_vad_model_path = asr_conf.get("vad_model_path", "")
            self.asr_num_threads = asr_conf.get("num_threads", 4)
            self.asr_language = asr_conf.get("language", "auto")
            self.asr_use_itn = asr_conf.get("use_itn", True)
            self.vad_threshold = asr_conf.get("vad_threshold", 0.5)
            self.silence_duration_ms = asr_conf.get("silence_duration_ms", 600)
            self.max_segment_duration = asr_conf.get("max_segment_duration", 10.0)

            llm_conf = raw["llm"]
            self.llm_provider = llm_conf["provider"]
            self.llm_api_key = llm_conf.get("api_key") or os.environ.get(llm_conf["api_key_env"]) or ""
            if not self.llm_api_key:
                raise ValueError(
                    f"Neither 'api_key' in config nor environment variable "
                    f"'{llm_conf['api_key_env']}' is set."
                )
            self.llm_model = llm_conf["model"]
            self.llm_selector_model = llm_conf.get("selector_model", llm_conf["model"])
            self.llm_base_url = llm_conf.get("base_url")
            self.llm_timeout = llm_conf.get("timeout", 10.0)
            self.llm_temperature = llm_conf["temperature"]
            self.llm_max_tokens = llm_conf["max_tokens"]

            viewer_conf = raw["viewer"]
            self.viewer_min_active = viewer_conf["min_active"]
            self.viewer_max_active = viewer_conf["max_active"]
            self.viewer_churn_per_tick = viewer_conf.get("churn_per_tick", 5)
            self.viewer_guider_ratio = viewer_conf.get("guider_ratio", 0.3)
            self.viewer_tick_interval_sec = viewer_conf["tick_interval_sec"]
        except KeyError as e:
            raise KeyError(f"Missing required config section/key in '{path}': {e}")


class _LazyConfig:
    _instance: Optional[Config] = None

    def __getattr__(self, name):
        if _LazyConfig._instance is None:
            _LazyConfig._instance = Config()
        return getattr(_LazyConfig._instance, name)


config: Config = _LazyConfig()  # type: ignore[assignment]
