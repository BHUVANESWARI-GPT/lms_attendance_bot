import asyncio
import calendar
import logging
from datetime import datetime, timedelta, timezone

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

from lms import LMSClient
import os
from dotenv import load_dotenv

load_dotenv()


# ==================================================
# BOT TOKEN
# ==================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")


# ==================================================
# USER SESSIONS
# ==================================================

sessions = {}

# Selected attendance information
attendance_data = {}


# ==================================================
# START
# ==================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 DOTE LMS Attendance Bot\n\n"
        "Commands:\n"
        "/login username password\n"
        "/status\n"
        "/attendance\n"
        "/logout"
    )


# ==================================================
# LOGIN
# ==================================================

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("LOGIN COMMAND RECEIVED")

    if len(context.args) != 2:
        await update.message.reply_text(
            "❌ Incorrect format.\n\n"
            "Use:\n"
            "/login username password"
        )
        return

    username, password = context.args

    # delete the message that contains the password
    try:
        await update.message.delete()
    except Exception:
        pass

    await context.bot.send_message(
        update.effective_chat.id, "🔐 Logging in to LMS..."
    )

    client = LMSClient()

    try:
        # We only use the single login method which runs the web flow
        ok = await client.login(username, password)

        if ok:
            sessions[update.effective_user.id] = client
            client.username = username  # store for later API calls
            await context.bot.send_message(
                update.effective_chat.id, "✅ LMS login successful.\n\nUse /attendance to continue."
            )
        else:
            await context.bot.send_message(
                update.effective_chat.id, "❌ LMS login failed."
            )

    except Exception as e:
        print("LOGIN ERROR:", e)
        await context.bot.send_message(
            update.effective_chat.id, "❌ Login error:\n" + str(e)
        )


# ==================================================
# STATUS
# ==================================================

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in sessions:
        await update.message.reply_text(
            "❌ Not logged in.\n\n"
            "Use:\n"
            "/login username password"
        )
        return

    client = sessions[user_id]

    if client.is_token_valid():
        await update.message.reply_text("✅ LMS session is active.")
    else:
        await update.message.reply_text("⚠️ Access token is missing or expired. (Will auto-refresh on next use or you can login again).")


# ==================================================
# ATTENDANCE MENU
# ==================================================

async def attendance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in sessions:
        await update.message.reply_text(
            "❌ Please login first.\n\n"
            "/login username password"
        )
        return

    keyboard = [
        [InlineKeyboardButton("📅 Today", callback_data="date_today")],
        [InlineKeyboardButton("📅 Yesterday", callback_data="date_yesterday")],
        [InlineKeyboardButton("📆 Custom Date", callback_data="date_custom")]
    ]

    await update.message.reply_text(
        "📅 <b>Select Attendance Date</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


# ==================================================
# DATE BUTTONS
# ==================================================

async def date_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if query.data == "date_today":
        selected_date = datetime.now().strftime("%Y-%m-%d")
        await show_subjects(query, user_id, selected_date)

    elif query.data == "date_yesterday":
        selected_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        await show_subjects(query, user_id, selected_date)

    elif query.data == "date_custom":
        now = datetime.now()
        await query.edit_message_text(
            "📆 Please select a date:",
            reply_markup=create_calendar(now.year, now.month)
        )


# ==================================================
# CALENDAR GENERATOR
# ==================================================

def create_calendar(year, month):
    keyboard = []
    
    # First row - Month and Year
    row = [InlineKeyboardButton(f"{calendar.month_name[month]} {year}", callback_data="ignore")]
    keyboard.append(row)
    
    # Second row - Week Days
    days = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
    row = [InlineKeyboardButton(day, callback_data="ignore") for day in days]
    keyboard.append(row)
    
    # Calendar rows - Days
    my_calendar = calendar.monthcalendar(year, month)
    for week in my_calendar:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="ignore"))
            else:
                row.append(InlineKeyboardButton(str(day), callback_data=f"calendar-day-{year}-{month}-{day}"))
        keyboard.append(row)
        
    # Last row - Navigation
    row = [
        InlineKeyboardButton("⬅️ Prev", callback_data=f"calendar-month-prev-{year}-{month}"),
        InlineKeyboardButton(" ", callback_data="ignore"),
        InlineKeyboardButton("Next ➡️", callback_data=f"calendar-month-next-{year}-{month}")
    ]
    keyboard.append(row)
    
    return InlineKeyboardMarkup(keyboard)


# ==================================================
# CALENDAR HANDLER
# ==================================================

async def calendar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    if data == "ignore":
        return
        
    if data.startswith("calendar-day-"):
        parts = data.split("-")
        year, month, day = int(parts[2]), int(parts[3]), int(parts[4])
        selected_date = f"{year:04d}-{month:02d}-{day:02d}"
        
        await query.edit_message_text(f"🔍 Getting subjects for {selected_date}...")
        await show_subjects(query, user_id, selected_date)
        
    elif data.startswith("calendar-month-prev-"):
        parts = data.split("-")
        year, month = int(parts[3]), int(parts[4])
        month -= 1
        if month < 1:
            month = 12
            year -= 1
        await query.edit_message_reply_markup(reply_markup=create_calendar(year, month))
        
    elif data.startswith("calendar-month-next-"):
        parts = data.split("-")
        year, month = int(parts[3]), int(parts[4])
        month += 1
        if month > 12:
            month = 1
            year += 1
        await query.edit_message_reply_markup(reply_markup=create_calendar(year, month))


# ==================================================
# SHOW SUBJECTS FROM CALLBACK
# ==================================================

async def show_subjects(query, user_id, selected_date):
    client = sessions[user_id]

    try:
        faculty_id = getattr(client, "username")
        data = await client.get_attendance(faculty_id)
        # data is a list of {date, timeSlots} objects
        subjects = extract_subjects(data, selected_date)

        if not subjects:
            await query.edit_message_text(f"❌ No subjects found for {selected_date}.")
            return

        # Group subjects by their batch_label (Class)
        classes_dict = {}
        for sub in subjects:
            lbl = sub.get("batch_label", "[Unknown]").strip("[] ")
            if not lbl: lbl = "Unknown"
            if lbl not in classes_dict:
                classes_dict[lbl] = []
            classes_dict[lbl].append(sub)

        # Convert to list for safe indexing (to avoid 64-byte callback limit)
        classes = [{"lbl": k, "subjects": v} for k, v in classes_dict.items()]

        attendance_data[user_id] = {
            "date": selected_date,
            "all_subjects": subjects,
            "classes": classes,
            "selected": set()
        }

        # If more than 1 class, ask user to pick class first
        if len(classes) > 1:
            await send_class_keyboard(query, user_id)
        else:
            # Only 1 class, go straight to subject selection
            attendance_data[user_id]["subjects"] = classes[0]["subjects"]
            await send_subject_keyboard(query, user_id)

    except Exception as e:
        print("SUBJECT ERROR:", e)
        await query.edit_message_text("❌ Error getting subjects:\n" + str(e))


# ==================================================
# EXTRACT SUBJECTS
# ==================================================

IST = timezone(timedelta(hours=5, minutes=30))

def extract_subjects(response_data, selected_date):
    subjects = []

    # response_data is a list of day-level objects: {date, timeSlots}
    for day_entry in response_data:

        # Convert UTC date to IST to get the local calendar date
        date_str = day_entry.get("date", "")
        try:
            dt_utc = datetime.fromisoformat(
                date_str.replace("Z", "+00:00")
            )
            entry_date = dt_utc.astimezone(IST).strftime("%Y-%m-%d")
        except Exception:
            entry_date = date_str[:10]

        if entry_date != selected_date:
            continue

        for slot in day_entry.get("timeSlots", []):

            task = slot.get("task")
            if not task:
                continue

            subject = task.get("courseTitle", "Unknown Subject")
            course_code = task.get("courseCode", "")
            task_id = task.get("taskId")
            start_time = slot.get("startTime", "")
            end_time = slot.get("endTime", "")
            section = task.get("section", "")
            prgm = task.get("prgmName", "")
            batch_year = task.get("batchYear", "")

            # Create a label for batch, section & prgm, e.g., "[2025-A | Diploma...]"
            parts = []
            if batch_year: parts.append(str(batch_year))
            if section: parts.append(str(section))
            
            batch_label = ""
            if parts and prgm:
                batch_label = f" [{'-'.join(parts)} | {prgm}]"
            elif parts:
                batch_label = f" [{'-'.join(parts)}]"
            elif prgm:
                batch_label = f" [{prgm}]"

            subjects.append({
                "subject": subject,
                "course_code": course_code,
                "task_id": task_id,
                "start": start_time,
                "end": end_time,
                "section": section,
                "batch_year": batch_year,
                "batch_label": batch_label,
                "prgm": prgm,
                "slot": slot
            })

    # Sort by start time
    subjects.sort(key=lambda x: x["start"])

    return subjects


# ==================================================
# CLASS KEYBOARD & CALLBACK
# ==================================================

async def send_class_keyboard(query, user_id):
    data = attendance_data[user_id]
    selected_date = data["date"]
    classes = data["classes"]

    keyboard = []
    for i, cls in enumerate(classes):
        keyboard.append([InlineKeyboardButton(f"\U0001f393 Class {cls['lbl']}", callback_data=f"class_{i}")])

    keyboard.append([InlineKeyboardButton("⬅️ Back to Calendar", callback_data="back_to_calendar")])

    await query.edit_message_text(
        f"📅 <b>{selected_date}</b>\n\n"
        "🎓 <b>Select a Class:</b>\n"
        "Filter subjects by class to mark bulk attendance.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def class_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = attendance_data.get(user_id)
    if not data: return

    idx = int(query.data.split("_", 1)[1])
    data["subjects"] = data["classes"][idx]["subjects"]
    data["selected"] = set()  # reset any previous selection

    await send_subject_keyboard(query, user_id)


# ==================================================
# SUBJECT KEYBOARD - CALLBACK
# ==================================================

async def send_subject_keyboard(query, user_id):
    data = attendance_data[user_id]
    selected_date = data["date"]
    subjects = data["subjects"]
    selected = data["selected"]

    keyboard = []
    for i, item in enumerate(subjects):
        symbol = "☑" if i in selected else "☐"
        status    = item["slot"].get("status", "")
        status_lbl = " 🟢" if status == "COMPLETED" else " 🟡" if status == "OPEN" else ""
        text = f"{symbol} {item['subject']}{item['batch_label']} ({item['start']}-{item['end']}){status_lbl}"
        keyboard.append([InlineKeyboardButton(text, callback_data=f"subject_{i}")])

    count = len(selected)
    if count > 0:
        keyboard.append([InlineKeyboardButton(
            f"▶️ Mark Attendance for {count} Period{'s' if count > 1 else ''}",
            callback_data="start_marking"
        )])

    # Actions row
    action_row = []
    if len(subjects) > 0 and count < len(subjects):
        action_row.append(InlineKeyboardButton("✅ Select All", callback_data="select_all_periods"))
    action_row.append(InlineKeyboardButton("🔄 Clear Selection", callback_data="clear_selection"))
    keyboard.append(action_row)

    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back_to_classes")])

    message = (
        f"📅 <b>{selected_date}</b>\n\n"
        "📚 <b>Tap periods to select:</b>\n\n"
        "☐ = Not selected  ☑ = Selected\n"
        "🟢 = COMPLETED  🟡 = NOT MARKED"
    )

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


# ==================================================
# SUBJECT SELECTION
# ==================================================

async def subject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = attendance_data.get(user_id)
    if not data:
        return

    index = int(query.data.split("_")[1])
    selected = data["selected"]

    if index in selected:
        selected.remove(index)
    else:
        selected.add(index)

    await send_subject_keyboard(query, user_id)


# ==================================================
# CLEAR SELECTION
# ==================================================

async def clear_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if user_id in attendance_data:
        attendance_data[user_id]["selected"].clear()

    await send_subject_keyboard(query, user_id)

# ==================================================
# SELECT ALL PERIODS
# ==================================================

async def select_all_periods(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = attendance_data.get(user_id)
    if not data: return
    
    # Select all available subjects
    data["selected"] = set(range(len(data["subjects"])))
    
    await send_subject_keyboard(query, user_id)


# ==================================================
# START MARKING — fetch all selected periods at once
# ==================================================

async def start_marking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = attendance_data.get(user_id)
    if not data:
        return

    selected_indices = sorted(data["selected"])
    if not selected_indices:
        await query.answer("Select at least one period first.", show_alert=True)
        return

    count = len(selected_indices)
    await query.edit_message_text(f"\u23f3 Fetching student list for {count} period{'s' if count > 1 else ''}...")

    client = sessions[user_id]
    period_data = []
    students    = None  # populated from the first period

    # Fetch all students in parallel
    fetch_tasks = [client.get_students(data["subjects"][idx]["task_id"]) for idx in selected_indices]
    fetch_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

    failed_periods = []
    for i, idx in enumerate(selected_indices):
        raw = fetch_results[i]
        if isinstance(raw, Exception):
            subject = data["subjects"][idx]
            failed_periods.append(f"- {subject['subject']} ({subject['start']})")

    if failed_periods:
        msg = "❌ <b>Failed to load student lists for the following periods:</b>\n" + "\n".join(failed_periods) + "\n\nPlease try again later or select fewer periods."
        await query.edit_message_text(msg, parse_mode="HTML")
        return

    for i, idx in enumerate(selected_indices):
        subject = data["subjects"][idx]
        slot    = subject["slot"]
        raw     = fetch_results[i]

        try:
            if isinstance(raw, list) and raw:
                wrapper       = raw[0]
                students_list = wrapper.get("attendanceDetail", [])
                task_details  = wrapper.get("taskDetails", LMSClient.build_task_details(slot))
            elif isinstance(raw, dict):
                students_list = raw.get("attendanceDetail", [])
                task_details  = raw.get("taskDetails", LMSClient.build_task_details(slot))
            else:
                students_list = []
                task_details  = LMSClient.build_task_details(slot)

            # Full objects keyed by rollNumber for this period
            student_objects = {s.get("rollNumber", "?"): dict(s) for s in students_list}

            # Use first period's student list as the reference for toggling
            if students is None:
                students = {
                    s.get("rollNumber", "?"): {
                        "name": s.get("name", "Unknown"),
                        "status": s.get("attendance", "Present")
                    }
                    for s in students_list
                }

            period_data.append({
                "idx":            idx,
                "task_details":   task_details,
                "student_objects": student_objects,
            })

        except Exception as e:
            print(f"Error processing period {idx} ({subject['subject']}):", e)

    if not period_data:
        await query.edit_message_text("\u274c Could not load any period. Please try again.")
        return

    data["period_data"] = period_data
    data["students"]    = students or {}

    await send_student_keyboard(query, user_id)




# ==================================================
# STUDENT KEYBOARD
# ==================================================

async def send_student_keyboard(query, user_id):
    data     = attendance_data[user_id]
    students = data["students"]

    keyboard = []
    for roll, info in students.items():
        symbol   = "\u2705" if info["status"] == "Present" else "\u274c"
        btn_text = f"{symbol} {info['name']}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"toggle_{roll}")])

    keyboard.append([
        InlineKeyboardButton("\u2705 All Present", callback_data="all_present"),
        InlineKeyboardButton("\u274c All Absent",  callback_data="all_absent"),
    ])
    keyboard.append([InlineKeyboardButton("\U0001f680 Submit Attendance", callback_data="preview_submit")])
    keyboard.append([InlineKeyboardButton("\u2b05\ufe0f Back to Periods",  callback_data="back_to_periods")])

    total   = len(students)
    present = sum(1 for s in students.values() if s["status"] == "Present")
    absent  = total - present

    selected_date = data["date"]
    period_data   = data.get("period_data", [])

    # Show which periods are being marked
    periods_txt = ""
    for pd in period_data:
        subj = data["subjects"][pd["idx"]]
        periods_txt += f"📚 <b>{subj['subject']}</b>{subj['batch_label']} ({subj['start']}–{subj['end']})\n"

    msg = (
        f"📅 <b>{selected_date}</b>\n"
        f"{periods_txt}\n"
        f"\u2705 Present: {present}  \u274c Absent: {absent}  \U0001f465 Total: {total}\n\n"
        "Tap a student to toggle Present/Absent:"
    )

    await query.edit_message_text(
        msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )


# ==================================================
# TOGGLE STUDENT
# ==================================================

async def toggle_student(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = attendance_data.get(user_id)
    if not data or "students" not in data:
        return

    roll = query.data[len("toggle_"):]
    if roll in data["students"]:
        current = data["students"][roll]["status"]
        data["students"][roll]["status"] = "Absent" if current == "Present" else "Present"

    await send_student_keyboard(query, user_id)


# ==================================================
# ALL PRESENT / ALL ABSENT
# ==================================================

async def all_present(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = attendance_data.get(user_id)
    if data and "students" in data:
        for roll in data["students"]:
            data["students"][roll]["status"] = "Present"
    await send_student_keyboard(query, user_id)


async def all_absent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = attendance_data.get(user_id)
    if data and "students" in data:
        for roll in data["students"]:
            data["students"][roll]["status"] = "Absent"
    await send_student_keyboard(query, user_id)


# ==================================================
# PREVIEW SUBMIT
# ==================================================

async def preview_submit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = attendance_data.get(user_id)
    if not data or "students" not in data:
        return

    students = data["students"]
    period_data = data.get("period_data", [])

    absent_students = []
    s_no = 1
    for roll, info in students.items():
        if info["status"] == "Absent":
            absent_students.append(f"{s_no}. {info['name']} ({roll})")
        s_no += 1

    periods_txt = ""
    for pd in period_data:
        subj = data["subjects"][pd["idx"]]
        periods_txt += f"📚 <b>{subj['subject']}</b>{subj['batch_label']} ({subj['start']}–{subj['end']})\n"

    absent_list_txt = "\n".join(absent_students) if absent_students else "<i>None (All Present)</i>"

    msg = (
        f"⚠️ <b>Confirm Submission</b> ⚠️\n\n"
        f"You are about to submit attendance for:\n{periods_txt}\n"
        f"<b>Absent Students:</b>\n{absent_list_txt}\n\n"
        f"Are you sure you want to save this to the official record?"
    )

    keyboard = [
        [InlineKeyboardButton("✅ Confirm & Save", callback_data="confirm_submit")],
        [InlineKeyboardButton("❌ Cancel", callback_data="back_to_periods")]
    ]

    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


# ==================================================
# CONFIRM SUBMIT (Actual Save)
# ==================================================

async def confirm_submit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = attendance_data.get(user_id)
    if not data or "students" not in data:
        return

    await query.edit_message_text("\u23f3 Submitting attendance...")

    client       = sessions[user_id]
    students     = data["students"]
    period_data  = data.get("period_data", [])

    if not period_data:
        # fallback (shouldn't be needed, but safe)
        period_data = [{
            "task_details": data.get("task_details"),
            "student_objects": data.get("student_objects", {}),
            "idx": data.get("current_idx", 0)
        }]

    try:
        submit_tasks = []
        for pd in period_data:
            pd_task = pd["task_details"]
            pd_objs = pd["student_objects"]

            full_detail = []
            for roll, info in students.items():
                if roll in pd_objs:
                    obj = dict(pd_objs[roll])
                    obj["attendance"] = info["status"]
                    full_detail.append(obj)
                else:
                    full_detail.append({"attendance": info["status"], "rollNumber": roll})

            submit_tasks.append(client.insert_attendance(pd_task, full_detail))

        # Run all submission requests in parallel
        submit_results = await asyncio.gather(*submit_tasks, return_exceptions=True)

        periods_txt = ""
        success_count = 0
        for idx, res in enumerate(submit_results):
            pd = period_data[idx]
            subj = data["subjects"][pd["idx"]]
            
            if isinstance(res, Exception):
                print(f"Error in period {pd['idx']}:", res)
                periods_txt += f"❌ <b>{subj['subject']}</b>{subj['batch_label']} ({subj['start']}–{subj['end']})\n"
            else:
                # Update local state so it shows as green checkmark
                if "slot" in subj:
                    subj["slot"]["status"] = "COMPLETED"
                success_count += 1
                periods_txt += f"✅ <b>{subj['subject']}</b>{subj['batch_label']} ({subj['start']}–{subj['end']})\n"
                print(f"Submitted period {pd['idx']} successfully")

        present = sum(1 for s in students.values() if s["status"] == "Present")
        absent  = len(students) - present
        selected_date = data["date"]

        status_msg = "✅ <b>Attendance Submitted!</b>" if success_count == len(period_data) else "⚠️ <b>Partial Submission</b>"

        await query.edit_message_text(
            f"{status_msg}\n\n"
            f"📅 <b>{selected_date}</b>\n"
            f"{periods_txt}\n"
            f"\u2705 Present : {present}\n"
            f"\u274c Absent  : {absent}\n"
            f"\U0001f465 Total   : {len(students)}",
            parse_mode="HTML"
        )

    except Exception as e:
        print("SUBMIT ERROR:", e)
        await query.edit_message_text(
            f"\u274c Submission failed entirely:\n{e}\n\nPlease try again."
        )


# ==================================================
# BACK NAVIGATION
# ==================================================

async def back_to_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    now = datetime.now()
    await query.edit_message_text(
        "📅 <b>Select Date:</b>\n"
        "Tap a date to mark attendance for that day.",
        reply_markup=create_calendar(now.year, now.month),
        parse_mode="HTML"
    )

async def back_to_classes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = attendance_data.get(user_id)
    if not data: return
    
    # If there's more than 1 class, go to classes, else calendar
    if len(data.get("classes", {})) > 1:
        await send_class_keyboard(query, user_id)
    else:
        await back_to_calendar(update, context)

async def back_to_periods(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = attendance_data.get(user_id)
    if data:
        data.pop("students", None)
        data.pop("period_data", None)
    await send_subject_keyboard(query, user_id)



# ==================================================
# LOGOUT
# ==================================================

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sessions.pop(user_id, None)
    attendance_data.pop(user_id, None)
    await update.message.reply_text("✅ LMS session removed.")


# ==================================================
# GLOBAL ERROR HANDLER
# ==================================================

async def error_handler(update, context):
    from telegram.error import NetworkError
    err = context.error
    # Silently ignore transient network drops (ReadError, NetworkError)
    if isinstance(err, NetworkError):
        return
    # Log everything else
    logging.getLogger(__name__).error("Unhandled error:", exc_info=err)


# ==================================================
# MAIN
# ==================================================

def main():
    print("================================")
    print("Starting Telegram LMS Bot")
    print("================================")

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("attendance", attendance))
    app.add_handler(CommandHandler("logout", logout))

    # Date buttons
    app.add_handler(CallbackQueryHandler(date_callback, pattern=r"^date_"))

    # Class selection
    app.add_handler(CallbackQueryHandler(class_callback, pattern=r"^class_"))

    # Subject buttons (select period)
    app.add_handler(CallbackQueryHandler(subject_callback, pattern=r"^subject_\d+$"))
    
    # Start marking, clear, and select all
    app.add_handler(CallbackQueryHandler(start_marking, pattern=r"^start_marking$"))
    app.add_handler(CallbackQueryHandler(clear_selection, pattern=r"^clear_selection$"))
    app.add_handler(CallbackQueryHandler(select_all_periods, pattern=r"^select_all_periods$"))

    # Student toggle
    app.add_handler(CallbackQueryHandler(toggle_student, pattern=r"^toggle_"))

    # All present / absent
    app.add_handler(CallbackQueryHandler(all_present, pattern=r"^all_present$"))
    app.add_handler(CallbackQueryHandler(all_absent,  pattern=r"^all_absent$"))

    # Submit & Confirmation
    app.add_handler(CallbackQueryHandler(preview_submit, pattern=r"^preview_submit$"))
    app.add_handler(CallbackQueryHandler(confirm_submit, pattern=r"^confirm_submit$"))

    # Navigation (Back buttons)
    app.add_handler(CallbackQueryHandler(back_to_calendar, pattern=r"^back_to_calendar$"))
    app.add_handler(CallbackQueryHandler(back_to_classes, pattern=r"^back_to_classes$"))
    app.add_handler(CallbackQueryHandler(back_to_periods, pattern=r"^back_to_periods$"))

    # Calendar buttons
    app.add_handler(CallbackQueryHandler(calendar_handler, pattern=r"^(calendar-|ignore)"))

    # Suppress noisy network errors (transient Telegram connection drops)
    app.add_error_handler(error_handler)

    print("Bot started...")
    print("Waiting for commands...")

    app.run_polling()


# ==================================================
# RUN
# ==================================================

if __name__ == "__main__":
    main()
