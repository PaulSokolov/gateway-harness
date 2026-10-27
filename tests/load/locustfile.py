"""Locust load test script for gateway latency and throughput benchmark."""

from locust import HttpUser, between, task


class GatewayUser(HttpUser):
    wait_time = between(0.01, 0.05)

    @task(5)
    def chat_simple(self):
        self.client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "What is the capital of France?"}],
            },
            headers={"Authorization": "Bearer sk-test-master-key"},
        )

    @task(2)
    def chat_templated(self):
        self.client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": "You are a customer service intent classifier."},
                    {"role": "user", "content": "I would like to cancel my subscription #59102"},
                ],
            },
            headers={"Authorization": "Bearer sk-test-master-key"},
        )
