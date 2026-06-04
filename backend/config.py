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
        try:
            with open(path) as f:
                raw = yaml.safe_load(f)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Config file not found at: {os.path.abspath(path)}. "
                "Set CONFIG_PATH env var or ensure the file exists."
            )
        except yaml.YAMLError as e:
            raise ValueError(f"Malformed YAML in config file '{path}': {e}")

        if raw is None:
            raise ValueError(f"Config file '{path}' is empty")

        try:
            server_conf = raw["server"]
            self.host = server_conf["host"]
            self.port = server_conf["port"]

            asr_conf = raw["asr"]
            self.asr_model_size = asr_conf["model_size"]
            self.asr_device = asr_conf["device"]
            self.asr_compute_type = asr_conf["compute_type"]
            self.asr_download_timeout = asr_conf.get("download_timeout", 30.0)

            llm_conf = raw["llm"]
            self.llm_provider = llm_conf["provider"]
            api_key_env = llm_conf["api_key_env"]
            api_key = os.environ.get(api_key_env)
            if not api_key:
                raise ValueError(
                    f"Environment variable '{api_key_env}' is not set. "
                    "Please set it to your API key."
                )
            self.llm_api_key = api_key
            self.llm_model = llm_conf["model"]
            self.llm_selector_model = llm_conf.get("selector_model", llm_conf["model"])
            self.llm_base_url = llm_conf.get("base_url")
            self.llm_timeout = llm_conf.get("timeout", 10.0)
            self.llm_temperature = llm_conf["temperature"]
            self.llm_max_tokens = llm_conf["max_tokens"]

            viewer_conf = raw["viewer"]
            self.viewer_min_active = viewer_conf["min_active"]
            self.viewer_max_active = viewer_conf["max_active"]
            self.viewer_entry_interval_sec = viewer_conf["entry_interval_sec"]
            self.viewer_cooldown_sec = viewer_conf["cooldown_sec"]
            self.viewer_memory_max_streamer_log = viewer_conf["memory_max_streamer_log"]
        except KeyError as e:
            raise KeyError(f"Missing required config section/key in '{path}': {e}")


class _LazyConfig:
    _instance: Optional[Config] = None

    def __getattr__(self, name):
        if _LazyConfig._instance is None:
            _LazyConfig._instance = Config()
        return getattr(_LazyConfig._instance, name)


config: Config = _LazyConfig()  # type: ignore[assignment]
