# Copyright (c) 2024, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from typing import Dict, List


class ContextManager:
    def __init__(self, max_context_length: int = 5):
        """
        Initialize the context manager with a limit for the number of past interactions to retain.
        :param max_context_length: Maximum number of past interactions to store (for context window)
        """
        self.max_context_length = max_context_length
        self.context = []  # Store the conversation history as a list of (user_query, agent_response) tuples

    def update_context(self, user_query: str, agent_response: str):
        """
        Update the context with a new user query and agent response.
        This will also manage the context length to ensure it doesn't exceed the max limit.
        :param user_query: The latest query from the user
        :param agent_response: The latest response from the agent
        """
        # Add the new interaction (user query + agent response) to the context
        self.context.append({"user_query": user_query, "agent_response": agent_response})

        # If the context exceeds the max length, trim it
        if len(self.context) > self.max_context_length:
            self.context.pop(0)  # Remove the oldest context

    def get_context(self) -> List[Dict[str, str]]:
        """
        Retrieve the current context (historical interactions).
        :return: A list of historical interactions in the form of user queries and agent responses.
        """
        return self.context

    def get_relevant_context(self, user_query: str) -> List[str]:
        """
        Retrieve relevant context to the current user query (e.g., the last N interactions).
        This method can be extended to use semantic similarity to retrieve more relevant history.
        :param user_query: The current user query
        :return: A list of relevant past queries/responses (filtered by context relevance).
        """
        # For simplicity, return the last N interactions
        # A more advanced version could use NLP-based techniques to rank relevance
        relevant_context = [interaction["agent_response"] for interaction in self.context]
        return relevant_context

    def reset_context(self):
        """
        Reset the context (e.g., at the start of a new session or after a long idle period).
        """
        self.context = []

    def get_context_summary(self) -> str:
        """
        Optionally, you can summarize the context (e.g., for chat-based systems).
        This could involve creating a summary of the user's past queries and agent's responses.
        :return: A summarized string of the context
        """
        return "\n".join([f"User: {entry['user_query']} \nAgent: {entry['agent_response']}" for entry in self.context])
