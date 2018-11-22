import os.path
import logging
import logging.config


def configure_logging(log_path):
    logging_conf = {
        'version': 1,
        'formatters': {
            'console': {'format': '%(asctime)s - %(levelname)s - %(message)s', 'datefmt': "%H:%M:%S"},
            "file": {"format": "%(asctime)-15s - %(name)-9s - %(levelname)-6s - %(message)s"}
        },
        'handlers': {
            'console': {
                'level': 'INFO',
                'class': 'logging.StreamHandler',
                'formatter': 'console',
                'stream': 'ext://sys.stdout'
            },
        },
        'loggers': {
        },
        "root": {
                'level': 'DEBUG',
                'handlers': ['console']
        },
        'disable_existing_loggers': False
    }
    if log_path:
        logging_conf["handlers"].update({
            'file': {
                'level': 'DEBUG',
                'class': 'logging.handlers.RotatingFileHandler',
                'formatter': 'file',
                'filename': log_path,
                'maxBytes': 1048576,
                'backupCount': 5,
                "encoding": "UTF-8"
            }
        })
        logging_conf.update(
            {
                "root": {
                'level': 'DEBUG',
                'handlers': ['console', 'file']
                }
            }
        )
        
    logging.config.dictConfig(logging_conf)

# log to dir of package but set actual logging loc to working dir when called as script (done in main)
configure_logging(None)