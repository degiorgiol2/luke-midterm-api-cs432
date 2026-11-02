import azure.functions as func
import json
import os
import uuid
from datetime import date
from azure.data.tables import TableClient
from azure.core.exceptions import ResourceNotFoundError

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


def get_table_client():
    connection_string = os.environ.get("AzureWebJobsStorage", "UseDevelopmentStorage=true")
    table_client = TableClient.from_connection_string(connection_string, table_name="tasks")
    try:
        table_client.create_table()
    except Exception:
        pass
    return table_client


def make_response(data, status_code=200):
    return func.HttpResponse(
        json.dumps(data),
        status_code=status_code,
        mimetype="application/json"
    )


def authorized(req):
    expected_key = os.environ.get("API_KEY")
    provided_key = req.headers.get("x-api-key")

    return bool(expected_key) and provided_key == expected_key


def read_json(req):
    try:
        return req.get_json()
    except (ValueError, TypeError):
        return None


def validate_task(data, creating=True):
    if not isinstance(data, dict):
        return "Request body must be a JSON object."

    if creating and "id" in data:
        return "Do not provide an id. The server generates it."

    if not isinstance(data.get("title"), str) or not data["title"].strip():
        return "Title is required and must not be empty."

    if data.get("priority") not in ["low", "medium", "high"]:
        return "Priority must be low, medium, or high."

    if data.get("status") not in ["todo", "in-progress", "done", "completed"]:
        return "Status must be todo, in-progress, done, or completed."

    if "dueDate" in data and data["dueDate"] is not None:
        if not isinstance(data["dueDate"], str):
            return "dueDate must use YYYY-MM-DD format."
        try:
            if date.fromisoformat(data["dueDate"]).isoformat() != data["dueDate"]:
                return "dueDate must use YYYY-MM-DD format."
        except ValueError:
            return "dueDate must use YYYY-MM-DD format."

    for field in ["category", "notes"]:
        if field in data and data[field] is not None:
            if not isinstance(data[field], str):
                return f"{field} must be a string."

    return None


def check_auth(req):
    if not authorized(req):
        return make_response(
            {"error": "Unauthorized. Provide a valid x-api-key header."},
            401
        )
    return None


@app.route(route="tasks", methods=["GET"])
def get_tasks(req: func.HttpRequest) -> func.HttpResponse:
    auth_error = check_auth(req)
    if auth_error:
        return auth_error

    table_client = get_table_client()
    tasks = []
    for entity in table_client.list_entities():
        tasks.append({
            "id": entity.get("RowKey"),
            "title": entity.get("title"),
            "priority": entity.get("priority"),
            "status": entity.get("status"),
            "dueDate": entity.get("dueDate"),
            "category": entity.get("category"),
            "notes": entity.get("notes")
        })

    return make_response(tasks)


@app.route(route="tasks", methods=["POST"])
def create_task(req: func.HttpRequest) -> func.HttpResponse:
    auth_error = check_auth(req)
    if auth_error:
        return auth_error

    data = read_json(req)
    error = validate_task(data)

    if error:
        return make_response({"error": error}, 400)

    task_id = str(uuid.uuid4())

    entity = {
        "PartitionKey": "Task",
        "RowKey": task_id,
        "title": data["title"].strip(),
        "priority": data["priority"],
        "status": data["status"],
        "dueDate": data.get("dueDate"),
        "category": data.get("category"),
        "notes": data.get("notes")
    }

    table_client = get_table_client()
    table_client.create_entity(entity)

    task = {
        "id": task_id,
        "title": entity["title"],
        "priority": entity["priority"],
        "status": entity["status"],
        "dueDate": entity["dueDate"],
        "category": entity["category"],
        "notes": entity["notes"]
    }

    return make_response(task, 201)


@app.route(route="tasks/{task_id}", methods=["PUT"])
def update_task(req: func.HttpRequest) -> func.HttpResponse:
    auth_error = check_auth(req)
    if auth_error:
        return auth_error

    task_id = req.route_params.get("task_id")
    table_client = get_table_client()

    try:
        table_client.get_entity(partition_key="Task", row_key=task_id)
    except ResourceNotFoundError:
        return make_response({"error": "Task not found."}, 404)

    data = read_json(req)
    error = validate_task(data, creating=False)

    if error:
        return make_response({"error": error}, 400)

    updated_entity = {
        "PartitionKey": "Task",
        "RowKey": task_id,
        "title": data["title"].strip(),
        "priority": data["priority"],
        "status": data["status"],
        "dueDate": data.get("dueDate"),
        "category": data.get("category"),
        "notes": data.get("notes")
    }

    table_client.update_entity(updated_entity, mode="replace")

    updated_task = {
        "id": task_id,
        "title": updated_entity["title"],
        "priority": updated_entity["priority"],
        "status": updated_entity["status"],
        "dueDate": updated_entity["dueDate"],
        "category": updated_entity["category"],
        "notes": updated_entity["notes"]
    }

    return make_response(updated_task, 200)


@app.route(route="tasks/{task_id}", methods=["DELETE"])
def delete_task(req: func.HttpRequest) -> func.HttpResponse:
    auth_error = check_auth(req)
    if auth_error:
        return auth_error

    task_id = req.route_params.get("task_id")
    table_client = get_table_client()

    try:
        entity = table_client.get_entity(partition_key="Task", row_key=task_id)
    except ResourceNotFoundError:
        return make_response({"error": "Task not found."}, 404)

    table_client.delete_entity(partition_key="Task", row_key=task_id)

    deleted_task = {
        "id": task_id,
        "title": entity.get("title"),
        "priority": entity.get("priority"),
        "status": entity.get("status"),
        "dueDate": entity.get("dueDate"),
        "category": entity.get("category"),
        "notes": entity.get("notes")
    }

    return make_response({
        "message": "Task deleted successfully.",
        "task": deleted_task
    })