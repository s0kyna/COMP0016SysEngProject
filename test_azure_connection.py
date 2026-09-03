import os
import asyncio
from dotenv import load_dotenv
from agent_framework.openai import OpenAIChatCompletionClient

load_dotenv()


async def main():
    client = OpenAIChatCompletionClient(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        model=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
    )

    response = await client.get_response(
        "Say hello and confirm that you are working."
    )

    print(response)


if __name__ == "__main__":
    asyncio.run(main())