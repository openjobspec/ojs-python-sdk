"""OJS serverless adapters for running job handlers in serverless environments.

Provides adapters for AWS Lambda and Azure Functions that bridge serverless
invocation events into OJS JobContext objects and handle ACK/NACK callbacks.

AWS Lambda (SQS trigger)::

    from ojs.serverless import LambdaHandler

    handler = LambdaHandler(ojs_url="https://ojs.example.com")

    @handler.register("email.send")
    async def handle_email(ctx):
        to = ctx.args[0]
        await send_email(to)

    # Entry point for Lambda
    lambda_handler = handler.sqs_handler

Azure Functions (Queue trigger)::

    from ojs.serverless import AzureFunctionsHandler

    handler = AzureFunctionsHandler(ojs_url="https://ojs.example.com")

    @handler.register("email.send")
    async def handle_email(ctx):
        to = ctx.args[0]
        await send_email(to)
"""

from ojs.serverless.aws_lambda import LambdaHandler
from ojs.serverless.azure_functions import AzureFunctionsHandler

__all__ = [
    "LambdaHandler",
    "AzureFunctionsHandler",
]
