import asyncio

from app.graph import run_agent


async def main() -> None:
    result = await run_agent("computer vision for medical imaging")

    print("Status:", result["status"])
    print("Results:")

    for candidate in result.get("results", []):
        print(candidate)


if __name__ == "__main__":
    asyncio.run(main())
