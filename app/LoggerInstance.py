import logging

logger = logging.getLogger("HUNNOI SERVICE")
logger.setLevel(logging.INFO)

if not logger.hasHandlers():
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)s - %(funcName)s] - %(message)s"
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)