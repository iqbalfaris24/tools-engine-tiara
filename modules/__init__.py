# modules/__init__.py
from .ssl_updater.tasks import run_ssl_deploy_task
from .deployment_parser.tasks import run_deployment_parse_task 
# from .data_migrator.tasks import run_migration_task

TASK_REGISTRY = {
    'ssl_deploy': run_ssl_deploy_task,
    'deployment_parse': run_deployment_parse_task,
}

def get_task_handler(task_type: str):
    handler = TASK_REGISTRY.get(task_type)
    if not handler:
        raise ValueError(f"No handler registered for task: {task_type}")
    return handler