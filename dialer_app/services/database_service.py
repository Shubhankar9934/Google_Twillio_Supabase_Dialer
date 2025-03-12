# dialer_app/services/database_service.py
import os
from supabase import create_client, Client

class DatabaseService:
    def __init__(self):
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY")
        if not self.supabase_url or not self.supabase_key:
            raise RuntimeError("Supabase URL and key must be set in the environment.")
        self.client: Client = create_client(self.supabase_url, self.supabase_key)

    def insert_call_record(self, call_record: dict):
        response = self.client.table("call_logs").insert(call_record).execute()
        print(f"[DatabaseService] Insert response: {response.data}")
