from fastapi import HTTPException


def fail(message, status=400):
    raise HTTPException(status, message)
