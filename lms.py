import httpx
import base64
import json
import time

class LMSClient:

    def __init__(self):
        # LMS
        self.base_url = "https://gptcsrirangam.tnedu.in"

        # Keycloak
        self.keycloak_base = "https://auth.tnedu.in/realms/gptcsrirangam"
        self.token_url = self.keycloak_base + "/protocol/openid-connect/token"

        # Token
        self.access_token = None
        self.refresh_token = None
        self.username = None
        self.password = None

        self.client = httpx.AsyncClient(timeout=30.0)

    # ==================================================
    # LOGIN (Direct ROPC - client_id: task)
    # ==================================================

    async def login(self, username, password):
        print("================================")
        print("Starting Login")
        print("Username:", username)
        print("================================")
        
        self.username = username
        self.password = password

        data = {
            "grant_type": "password",
            "client_id": "task",
            "username": username,
            "password": password
        }

        try:
            response = await self.client.post(self.token_url, data=data)
            print("Keycloak Status:", response.status_code)

            if response.status_code != 200:
                print("Keycloak response:", response.text)
                return False

            token_data = response.json()
            if "access_token" not in token_data:
                print("Access token not found.")
                return False

            self.access_token = token_data["access_token"]
            self.refresh_token = token_data.get("refresh_token")

            print("================================")
            print("LOGIN SUCCESSFUL (azp=task)")
            print("================================")
            return True

        except httpx.RequestError as e:
            print("Connection error:", e)
            return False

    # ==================================================
    # TOKEN MANAGEMENT
    # ==================================================

    def get_jwt_payload(self):
        if not self.access_token:
            return "{}"
        parts = self.access_token.split('.')
        if len(parts) != 3:
            return "{}"
        payload = parts[1]
        payload += '=' * (-len(payload) % 4)
        return base64.b64decode(payload).decode('utf-8')

    def is_token_valid(self):
        if not self.access_token:
            return False
        try:
            payload = json.loads(self.get_jwt_payload())
            exp = payload.get("exp", 0)
            # Add a 10-second buffer
            if time.time() < (exp - 10):
                return True
            return False
        except Exception:
            return False

    async def refresh_session(self):
        print("Attempting to refresh token...")
        if not self.refresh_token:
            print("No refresh token available.")
            return False
            
        data = {
            "grant_type": "refresh_token",
            "client_id": "task",
            "refresh_token": self.refresh_token
        }
        try:
            response = await self.client.post(self.token_url, data=data)
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data["access_token"]
                self.refresh_token = token_data.get("refresh_token", self.refresh_token)
                print("Token refreshed successfully.")
                return True
            else:
                print("Refresh failed, attempting full re-login...")
                return await self.login(self.username, self.password)
        except httpx.RequestError as e:
            print("Refresh connection error:", e)
            return False

    def _api_headers(self, referer_path="/task-ui/classAttendance"):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json, text/plain, */*",
            "Origin": self.base_url,
            "Referer": self.base_url + referer_path,
            "userdetails": self.get_jwt_payload(),
        }

    async def _request(self, method, url, referer_path="/task-ui/classAttendance", **kwargs):
        if not self.is_token_valid():
            print("Token expired before request, refreshing...")
            success = await self.refresh_session()
            if not success:
                raise Exception("Not logged in. Token expired and refresh failed.")
                
        headers = self._api_headers(referer_path)
        if "json" in kwargs or "data" in kwargs:
            headers["Content-Type"] = "application/json"
            
        kwargs["headers"] = headers
        
        response = await self.client.request(method, url, **kwargs)
        
        # If 401, maybe the token died despite our check
        if response.status_code == 401:
            print("Got 401 Unauthorized, refreshing token and retrying...")
            success = await self.refresh_session()
            if success:
                kwargs["headers"] = self._api_headers(referer_path)
                if "json" in kwargs or "data" in kwargs:
                    kwargs["headers"]["Content-Type"] = "application/json"
                response = await self.client.request(method, url, **kwargs)
                
        return response

    # ==================================================
    # GET ATTENDANCE LIST (all periods for faculty)
    # ==================================================

    async def get_attendance(self, faculty_id):
        url = self.base_url + f"/task/task/attendance/{faculty_id}/ATTENDANCE%20ENTRY"
        response = await self._request("GET", url, referer_path="/task-ui/classAttendance")
        
        print("Attendance GET Status:", response.status_code)
        if response.status_code != 200:
            print(response.text)
            raise Exception(f"Attendance GET failed: {response.status_code}")
        return response.json()

    # ==================================================
    # GET STUDENTS for a specific task
    # ==================================================

    async def get_students(self, task_id):
        url = self.base_url + f"/task/attendance/fetch/{task_id}"
        referer = f"/task-ui/markAttendance/{task_id}"
        response = await self._request("GET", url, referer_path=referer)

        print("Students GET Status:", response.status_code, "for task", task_id)
        if response.status_code != 200:
            raise Exception(f"Students GET failed: {response.status_code} - {response.text[:500]}")

        data = response.json()
        return data

    # ==================================================
    # SUBMIT ATTENDANCE
    # ==================================================

    async def insert_attendance(self, task_details, attendance_detail):
        url = self.base_url + "/task/attendance/insert"
        task_id = task_details.get("_id", "")
        referer = f"/task-ui/markAttendance/{task_id}"

        payload = {
            "attendanceDetail": [{
                "attendanceDetail": attendance_detail,
                "taskDetails": task_details
            }]
        }

        print("Submitting attendance for task:", task_id)
        response = await self._request("POST", url, referer_path=referer, json=payload)

        print("Attendance POST Status:", response.status_code)
        if response.status_code not in (200, 201):
            print(response.text)
            raise Exception(f"Attendance submission failed: {response.status_code} - {response.text[:300]}")

        return response.json()

    # ==================================================
    # BUILD taskDetails
    # ==================================================
    @staticmethod
    def build_task_details(slot):
        task = slot.get("task", {})
        return {
            "_id":           task.get("taskId"),
            "termId":        task.get("termId") or slot.get("termId"),
            "workloadId":    slot.get("workloadId"),
            "timeTableId":   slot.get("timeTableId"),
            "scheduleId":    slot.get("scheduleId"),
            "faculty":                 slot.get("attendanceEntryFaculty", []),
            "attendanceEntryFaculty":  slot.get("attendanceEntryFaculty", []),
            "date":      slot.get("date"),
            "dayOrder":  slot.get("dayOrder"),
            "session":   slot.get("session"),
            "startTime": slot.get("startTime"),
            "endTime":   slot.get("endTime"),
            "course": {
                "id":    task.get("courseId"),
                "code":  task.get("courseCode"),
                "title": task.get("courseTitle"),
            },
            "class": {
                "dept": slot.get("dept"),
                "prgm": {
                    "id":       task.get("prgmId"),
                    "name":     task.get("prgmName"),
                    "category": task.get("category"),
                    "mode":     "REGULAR",
                },
                "section": {
                    "id":   task.get("sectionId"),
                    "name": task.get("section"),
                },
                "batch": {
                    "id":   task.get("batchId"),
                    "year": task.get("batchYear"),
                },
                "group": task.get("group"),
            },
            "source":     slot.get("source"),
            "status":     slot.get("status"),
            "isAcademic": True,
            "location":   slot.get("location"),
        }
