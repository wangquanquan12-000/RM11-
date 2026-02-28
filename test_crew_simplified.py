# -*- coding: utf-8 -*-
import os
from crewai import Agent, Task, Crew
from langchain_google_genai import ChatGoogleGenerativeAI

gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    raise ValueError("ERROR: GEMINI_API_KEY environment variable is not set. Please set it and try again.")

llm = ChatGoogleGenerativeAI(model="gemini-pro", google_api_key=gemini_api_key, temperature=0.0)

test_agent = Agent(
    role='Tester',
    goal='Test the LLM.',
    backstory='You are a tester.',
    llm=llm,
    verbose=True,
    allow_delegation=False,
)

test_task = Task(
    description="Simply say 'Hello, World!'",
    expected_output="The string 'Hello, World!'",
    agent=test_agent
)

crew = Crew(
    agents=[test_agent],
    tasks=[test_task],
    verbose=True
)

if __name__ == "__main__":
    result = crew.kickoff()
    print(result)
