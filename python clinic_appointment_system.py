import tkinter as tk
from tkinter import messagebox
import sqlite3
import datetime
import gc


# =========================
# Custom Exceptions
# =========================
class ClinicError(Exception):
    pass


class ValidationError(ClinicError):
    pass


class NotFoundError(ClinicError):
    pass


class ConflictError(ClinicError):
    pass


class DatabaseError(ClinicError):
    pass


# =========================
# Domain Model (OOP Core)
# =========================
class Person:

    system_name = "Clinic Appointment System"

    def __init__(self, full_name, phone):
        self._full_name = full_name
        self._phone = phone

    def get_full_name(self):
        return self._full_name

    def set_full_name(self, value):
        if not value or not value.strip():
            raise ValidationError("Full name cannot be empty.")
        self._full_name = value.strip()

    def get_phone(self):
        return self._phone

    def set_phone(self, value):
        if not value or not value.strip():
            raise ValidationError("Phone cannot be empty.")
        self._phone = value.strip()

    def get_role(self):
        raise NotImplementedError("Subclass must implement get_role().")

    def display_summary(self):
        return f"{self.get_role()}: {self._full_name} ({self._phone})"

    @classmethod
    def get_system_name(cls):
        return cls.system_name


class Patient(Person):

    def __init__(self, full_name, phone, ic_number, address=""):
        super().__init__(full_name, phone)
        self.__ic_number = ic_number
        self.__address = address

    def get_role(self):
        return "Patient"

    def get_ic_number(self):
        return self.__ic_number

    def set_ic_number(self, value):
        if not value or not value.strip():
            raise ValidationError("IC number cannot be empty.")
        self.__ic_number = value.strip()

    def get_address(self):
        return self.__address

    def set_address(self, value):
        self.__address = (value or "").strip()

    def display_summary(self):
        return f"Patient: {self.get_full_name()} | Phone: {self.get_phone()} | IC: {self.get_ic_number()}"


class Staff(Person):

    def __init__(self, full_name, phone, staff_id):
        super().__init__(full_name, phone)
        self._staff_id = staff_id  

    def get_staff_id(self):
        return self._staff_id

    def set_staff_id(self, value):
        if not value or not value.strip():
            raise ValidationError("Staff ID cannot be empty.")
        self._staff_id = value.strip()

    def get_role(self):
        raise NotImplementedError("Subclass must implement get_role().")


class Doctor(Staff):
    def __init__(self, full_name, phone, staff_id, specialization, consultation_fee=0.0):
        super().__init__(full_name, phone, staff_id)
        self.__specialization = specialization
        self.__consultation_fee = float(consultation_fee)

    def get_role(self):
        return "Doctor"

    def get_specialization(self):
        return self.__specialization

    def set_specialization(self, value):
        if not value or not value.strip():
            raise ValidationError("Specialization cannot be empty.")
        self.__specialization = value.strip()

    def get_consultation_fee(self):
        return self.__consultation_fee

    def set_consultation_fee(self, value):
        try:
            fee = float(value)
        except:
            raise ValidationError("Consultation fee must be a number.")
        if fee < 0:
            raise ValidationError("Consultation fee cannot be negative.")
        self.__consultation_fee = fee

    def display_summary(self):
        return (
            f"Doctor: {self.get_full_name()} | StaffID: {self.get_staff_id()} | "
            f"Spec: {self.get_specialization()} | Fee: RM{self.get_consultation_fee():.2f}"
        )


class Appointment:
    STATUS_PENDING = "PENDING"
    STATUS_CONFIRMED = "CONFIRMED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_COMPLETED = "COMPLETED"

    def __init__(self, patient_id, doctor_id, appt_datetime, reason, status=STATUS_PENDING):
        self.__patient_id = int(patient_id)
        self.__doctor_id = int(doctor_id)
        self.__appt_datetime = appt_datetime  
        self.__reason = (reason or "").strip()
        self.__status = status

    def get_patient_id(self):
        return self.__patient_id

    def get_doctor_id(self):
        return self.__doctor_id

    def get_datetime(self):
        return self.__appt_datetime

    def set_datetime(self, new_dt):
        if not isinstance(new_dt, datetime.datetime):
            raise ValidationError("Invalid appointment datetime.")
        self.__appt_datetime = new_dt

    def get_reason(self):
        return self.__reason

    def set_reason(self, value):
        self.__reason = (value or "").strip()

    def get_status(self):
        return self.__status

    def set_status(self, value):
        allowed = [
            self.STATUS_PENDING,
            self.STATUS_CONFIRMED,
            self.STATUS_CANCELLED,
            self.STATUS_COMPLETED,
        ]
        if value not in allowed:
            raise ValidationError("Invalid status.")
        self.__status = value

    def cancel(self):
        if self.__status == self.STATUS_COMPLETED:
            raise ValidationError("Cannot cancel a completed appointment.")
        self.__status = self.STATUS_CANCELLED

    def confirm(self):
        if self.__status in [self.STATUS_CANCELLED, self.STATUS_COMPLETED]:
            raise ValidationError("Cannot confirm cancelled/completed appointment.")
        self.__status = self.STATUS_CONFIRMED

    def complete(self):
        if self.__status == self.STATUS_CANCELLED:
            raise ValidationError("Cannot complete a cancelled appointment.")
        self.__status = self.STATUS_COMPLETED


class Procedure:

    def __init__(self, patient_id, procedure_name, procedure_date, practitioner, charges, appointment_id=None):
        self.__patient_id = int(patient_id)
        self.__procedure_name = (procedure_name or "").strip()
        self.__procedure_date = (procedure_date or "").strip() 
        self.__practitioner = (practitioner or "").strip()
        self.__charges = float(charges)
        self.__appointment_id = appointment_id

    def get_patient_id(self):
        return self.__patient_id

    def get_procedure_name(self):
        return self.__procedure_name

    def get_procedure_date(self):
        return self.__procedure_date

    def get_practitioner(self):
        return self.__practitioner

    def get_charges(self):
        return self.__charges

    def get_appointment_id(self):
        return self.__appointment_id


# =========================
# Database Layer
# =========================
class DatabaseManager:
    def __init__(self, db_path="clinic.db"):
        self.__db_path = db_path
        self.__conn = None

    def connect(self):
        try:
            self.__conn = sqlite3.connect(self.__db_path)
            self.__conn.execute("PRAGMA foreign_keys = ON;")
        except Exception as e:
            raise DatabaseError(f"Failed to connect database: {e}")

    def close(self):
        if self.__conn:
            self.__conn.close()
            self.__conn = None

    def get_conn(self):
        if not self.__conn:
            raise DatabaseError("Database not connected.")
        return self.__conn

    def init_tables(self):
        conn = self.get_conn()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS patients (
                    patient_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    ic_number TEXT NOT NULL,
                    address TEXT
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS doctors (
                    doctor_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    staff_id TEXT NOT NULL,
                    specialization TEXT NOT NULL,
                    consultation_fee REAL NOT NULL DEFAULT 0
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS appointments (
                    appointment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER NOT NULL,
                    doctor_id INTEGER NOT NULL,
                    appt_datetime TEXT NOT NULL,
                    reason TEXT,
                    status TEXT NOT NULL,
                    FOREIGN KEY(patient_id) REFERENCES patients(patient_id),
                    FOREIGN KEY(doctor_id) REFERENCES doctors(doctor_id)
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS procedures (
                    procedure_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER NOT NULL,
                    appointment_id INTEGER,
                    procedure_name TEXT NOT NULL,
                    procedure_date TEXT NOT NULL,
                    practitioner TEXT NOT NULL,
                    charges REAL NOT NULL,
                    FOREIGN KEY(patient_id) REFERENCES patients(patient_id),
                    FOREIGN KEY(appointment_id) REFERENCES appointments(appointment_id)
                );
                """
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise DatabaseError(f"Failed to init tables: {e}")


class PatientRepository:
    def __init__(self, db):
        self._db = db

    def add(self, patient):
        conn = self._db.get_conn()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO patients (full_name, phone, ic_number, address) VALUES (?, ?, ?, ?)",
                (patient.get_full_name(), patient.get_phone(), patient.get_ic_number(), patient.get_address()),
            )
            conn.commit()
            return cur.lastrowid
        except Exception as e:
            conn.rollback()
            raise DatabaseError(f"Failed to add patient: {e}")

    def list_all(self):
        conn = self._db.get_conn()
        cur = conn.cursor()
        cur.execute("SELECT patient_id, full_name, phone, ic_number, address FROM patients ORDER BY patient_id DESC")
        return cur.fetchall()

    def find_by_id(self, patient_id):
        conn = self._db.get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT patient_id, full_name, phone, ic_number, address FROM patients WHERE patient_id=?",
            (patient_id,),
        )
        row = cur.fetchone()
        if not row:
            raise NotFoundError("Patient not found.")
        return row


class DoctorRepository:
    def __init__(self, db):
        self._db = db

    def add(self, doctor):
        conn = self._db.get_conn()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO doctors (full_name, phone, staff_id, specialization, consultation_fee) VALUES (?, ?, ?, ?, ?)",
                (
                    doctor.get_full_name(),
                    doctor.get_phone(),
                    doctor.get_staff_id(),
                    doctor.get_specialization(),
                    doctor.get_consultation_fee(),
                ),
            )
            conn.commit()
            return cur.lastrowid
        except Exception as e:
            conn.rollback()
            raise DatabaseError(f"Failed to add doctor: {e}")

    def list_all(self):
        conn = self._db.get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT doctor_id, full_name, phone, staff_id, specialization, consultation_fee FROM doctors ORDER BY doctor_id DESC"
        )
        return cur.fetchall()

    def find_by_id(self, doctor_id):
        conn = self._db.get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT doctor_id, full_name, phone, staff_id, specialization, consultation_fee FROM doctors WHERE doctor_id=?",
            (doctor_id,),
        )
        row = cur.fetchone()
        if not row:
            raise NotFoundError("Doctor not found.")
        return row


class AppointmentRepository:
    def __init__(self, db):
        self._db = db

    def add(self, appt):
        conn = self._db.get_conn()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO appointments (patient_id, doctor_id, appt_datetime, reason, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    appt.get_patient_id(),
                    appt.get_doctor_id(),
                    appt.get_datetime().strftime("%Y-%m-%d %H:%M"),
                    appt.get_reason(),
                    appt.get_status(),
                ),
            )
            conn.commit()
            return cur.lastrowid
        except Exception as e:
            conn.rollback()
            raise DatabaseError(f"Failed to add appointment: {e}")

    def update_status(self, appointment_id, new_status):
        conn = self._db.get_conn()
        try:
            conn.execute("UPDATE appointments SET status=? WHERE appointment_id=?", (new_status, appointment_id))
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise DatabaseError(f"Failed to update status: {e}")

    def update_datetime(self, appointment_id, new_dt):
        conn = self._db.get_conn()
        try:
            conn.execute(
                "UPDATE appointments SET appt_datetime=? WHERE appointment_id=?",
                (new_dt.strftime("%Y-%m-%d %H:%M"), appointment_id),
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise DatabaseError(f"Failed to reschedule: {e}")

    def list_all(self):
        conn = self._db.get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT a.appointment_id, a.appt_datetime, a.status, a.reason,
                   p.patient_id, p.full_name,
                   d.doctor_id, d.full_name
            FROM appointments a
            JOIN patients p ON a.patient_id = p.patient_id
            JOIN doctors d ON a.doctor_id = d.doctor_id
            ORDER BY a.appt_datetime DESC
            """
        )
        return cur.fetchall()

    def find_by_id(self, appointment_id):
        conn = self._db.get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT appointment_id, patient_id, doctor_id, appt_datetime, reason, status FROM appointments WHERE appointment_id=?",
            (appointment_id,),
        )
        row = cur.fetchone()
        if not row:
            raise NotFoundError("Appointment not found.")
        return row

    def check_conflict(self, doctor_id, appt_dt, ignore_appointment_id=None):
        conn = self._db.get_conn()
        cur = conn.cursor()
        dt_str = appt_dt.strftime("%Y-%m-%d %H:%M")

        if ignore_appointment_id:
            cur.execute(
                """
                SELECT appointment_id FROM appointments
                WHERE doctor_id=? AND appt_datetime=? AND status IN ('PENDING','CONFIRMED')
                AND appointment_id <> ?
                """,
                (doctor_id, dt_str, ignore_appointment_id),
            )
        else:
            cur.execute(
                """
                SELECT appointment_id FROM appointments
                WHERE doctor_id=? AND appt_datetime=? AND status IN ('PENDING','CONFIRMED')
                """,
                (doctor_id, dt_str),
            )

        row = cur.fetchone()
        return row is not None


class ProcedureRepository:
    def __init__(self, db):
        self._db = db

    def add(self, procedure):
        conn = self._db.get_conn()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO procedures (patient_id, appointment_id, procedure_name, procedure_date, practitioner, charges)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    procedure.get_patient_id(),
                    procedure.get_appointment_id(),
                    procedure.get_procedure_name(),
                    procedure.get_procedure_date(),
                    procedure.get_practitioner(),
                    procedure.get_charges(),
                ),
            )
            conn.commit()
            return cur.lastrowid
        except Exception as e:
            conn.rollback()
            raise DatabaseError(f"Failed to add procedure: {e}")

    def list_by_patient(self, patient_id):
        conn = self._db.get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT procedure_id, procedure_name, procedure_date, practitioner, charges, appointment_id
            FROM procedures
            WHERE patient_id=?
            ORDER BY procedure_id DESC
            """,
            (patient_id,),
        )
        return cur.fetchall()

    def total_charges_by_patient(self, patient_id):
        conn = self._db.get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(SUM(charges),0) FROM procedures WHERE patient_id=?", (patient_id,))
        return float(cur.fetchone()[0])


# =========================
# Service Layer (Business Logic)
# =========================
class ClinicService:
    def __init__(self, db):
        self._db = db
        self.patients = PatientRepository(db)
        self.doctors = DoctorRepository(db)
        self.appointments = AppointmentRepository(db)
        self.procedures = ProcedureRepository(db)

    @staticmethod
    def parse_datetime(dt_str):
        # expecting: YYYY-MM-DD HH:MM
        try:
            return datetime.datetime.strptime(dt_str.strip(), "%Y-%m-%d %H:%M")
        except:
            raise ValidationError("Datetime must be in format YYYY-MM-DD HH:MM (example: 2026-01-02 14:30).")

    def register_patient(self, full_name, phone, ic_number, address):
        p = Patient(full_name, phone, ic_number, address)
        return self.patients.add(p)

    def add_doctor(self, full_name, phone, staff_id, specialization, fee):
        d = Doctor(full_name, phone, staff_id, specialization, fee)
        return self.doctors.add(d)

    def book_appointment(self, patient_id, doctor_id, dt_str, reason):
        dt = self.parse_datetime(dt_str)

        if dt < datetime.datetime.now():
            raise ValidationError("Appointment datetime cannot be in the past.")

        self.patients.find_by_id(patient_id)
        self.doctors.find_by_id(doctor_id)

        if self.appointments.check_conflict(doctor_id, dt):
            raise ConflictError("Time slot conflict: Doctor already has an appointment at that time.")

        appt = Appointment(patient_id, doctor_id, dt, reason, Appointment.STATUS_PENDING)
        return self.appointments.add(appt)

    def change_status(self, appointment_id, new_status):
        row = self.appointments.find_by_id(appointment_id)
        # row: appointment_id, patient_id, doctor_id, appt_datetime, reason, status
        appt = Appointment(row[1], row[2], self.parse_datetime(row[3]), row[4], row[5])
        appt.set_status(new_status)
        self.appointments.update_status(appointment_id, appt.get_status())

    def reschedule(self, appointment_id, new_dt_str):
        row = self.appointments.find_by_id(appointment_id)
        current_status = row[5]
        if current_status in [Appointment.STATUS_CANCELLED, Appointment.STATUS_COMPLETED]:
            raise ValidationError("Cannot reschedule cancelled/completed appointment.")

        new_dt = self.parse_datetime(new_dt_str)
        if new_dt < datetime.datetime.now():
            raise ValidationError("New datetime cannot be in the past.")

        doctor_id = row[2]
        if self.appointments.check_conflict(doctor_id, new_dt, ignore_appointment_id=appointment_id):
            raise ConflictError("Time slot conflict: Doctor already has an appointment at that time.")

        self.appointments.update_datetime(appointment_id, new_dt)

    def add_procedure_for_patient(self, patient_id, procedure_name, procedure_date, practitioner, charges, appointment_id=None):
        # basic validation
        if not procedure_name.strip():
            raise ValidationError("Procedure name cannot be empty.")
        self.patients.find_by_id(patient_id)

        try:
            datetime.datetime.strptime(procedure_date.strip(), "%Y-%m-%d")
        except:
            raise ValidationError("Procedure date must be YYYY-MM-DD.")

        try:
            charges = float(charges)
        except:
            raise ValidationError("Charges must be a number.")

        if charges < 0:
            raise ValidationError("Charges cannot be negative.")

        proc = Procedure(patient_id, procedure_name, procedure_date, practitioner, charges, appointment_id)
        return self.procedures.add(proc)


# =========================
# GUI Layer (Tkinter)
# =========================
class ClinicAppGUI:
    def __init__(self):
        self.db = DatabaseManager("clinic.db")
        self.db.connect()
        self.db.init_tables()

        self.service = ClinicService(self.db)

        self.root = tk.Tk()
        self.root.title(Person.get_system_name())
        self.root.geometry("1000x650")

        self.left_menu = tk.Frame(self.root, borderwidth=1, relief="solid")
        self.left_menu.pack(side="left", fill="y")

        self.main_area = tk.Frame(self.root, borderwidth=1, relief="solid")
        self.main_area.pack(side="left", fill="both", expand=True)

        self.status_var = tk.StringVar()
        self.status_var.set("Ready.")

        self.status_bar = tk.Label(self.root, textvariable=self.status_var, anchor="w", borderwidth=1, relief="solid")
        self.status_bar.pack(side="bottom", fill="x")

        self._build_menu()
        self._show_home()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        tk.mainloop()

    def _on_close(self):
        try:
            self.db.close()
        except:
            pass
        self.root.destroy()

    def _set_status(self, text):
        self.status_var.set(text)

    def _clear_main(self):
        for widget in self.main_area.winfo_children():
            widget.destroy()

    def _build_menu(self):
        title = tk.Label(self.left_menu, text="MENU", padx=10, pady=10)
        title.pack()

        btn_home = tk.Button(self.left_menu, text="Home", width=18, command=self._show_home)
        btn_home.pack(pady=5)

        btn_pat = tk.Button(self.left_menu, text="Patients", width=18, command=self._show_patients)
        btn_pat.pack(pady=5)

        btn_doc = tk.Button(self.left_menu, text="Doctors", width=18, command=self._show_doctors)
        btn_doc.pack(pady=5)

        btn_appt = tk.Button(self.left_menu, text="Appointments", width=18, command=self._show_appointments)
        btn_appt.pack(pady=5)

        btn_proc = tk.Button(self.left_menu, text="Procedures/Billing", width=18, command=self._show_procedures)
        btn_proc.pack(pady=5)

        btn_analytics = tk.Button(self.left_menu, text="Analytics", width=18, command=self._show_analytics)
        btn_analytics.pack(pady=5)

        btn_gc = tk.Button(self.left_menu, text="GC Tools", width=18, command=self._show_gc_tools)
        btn_gc.pack(pady=5)

        btn_quit = tk.Button(self.left_menu, text="Quit", width=18, command=self.root.destroy)
        btn_quit.pack(pady=20)

    def _show_home(self):
        self._clear_main()
        header = tk.Label(self.main_area, text="Clinic Appointment System", font=("Arial", 16), pady=10)
        header.pack()

        info = tk.Label(
            self.main_area,
            text="This system manages Patients, Doctors, Appointments, and basic Billing (Procedures).",
            pady=10,
        )
        info.pack()

        tips = tk.Label(
            self.main_area,
            text="Tip: Run this program using VS Code or Terminal for best stability.",
            pady=10,
        )
        tips.pack()

        try:
            total_pat = len(self.service.patients.list_all())
            total_doc = len(self.service.doctors.list_all())
            total_appt = len(self.service.appointments.list_all())
        except Exception as e:
            total_pat = total_doc = total_appt = 0

        stats = tk.Label(
            self.main_area,
            text=f"Quick Stats: Patients={total_pat} | Doctors={total_doc} | Appointments={total_appt}",
            pady=10,
        )
        stats.pack()

    # -------------------------
    # Patients Page
    # -------------------------
    def _show_patients(self):
        self._clear_main()
        header = tk.Label(self.main_area, text="Patients", font=("Arial", 14), pady=10)
        header.pack()

        form = tk.Frame(self.main_area)
        form.pack(pady=5, fill="x")

        tk.Label(form, text="Full Name").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        tk.Label(form, text="Phone").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        tk.Label(form, text="IC Number").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        tk.Label(form, text="Address").grid(row=3, column=0, sticky="w", padx=5, pady=2)

        name_entry = tk.Entry(form, width=40)
        phone_entry = tk.Entry(form, width=40)
        ic_entry = tk.Entry(form, width=40)
        addr_entry = tk.Entry(form, width=40)

        name_entry.grid(row=0, column=1, padx=5, pady=2)
        phone_entry.grid(row=1, column=1, padx=5, pady=2)
        ic_entry.grid(row=2, column=1, padx=5, pady=2)
        addr_entry.grid(row=3, column=1, padx=5, pady=2)

        btn_frame = tk.Frame(self.main_area)
        btn_frame.pack(pady=5)

        def add_patient():
            try:
                pid = self.service.register_patient(
                    name_entry.get(),
                    phone_entry.get(),
                    ic_entry.get(),
                    addr_entry.get(),
                )
                messagebox.showinfo("Success", f"Patient added. ID = {pid}")
                self._set_status(f"Added patient ID {pid}")
                self._refresh_patients_list(listbox)
            except Exception as e:
                messagebox.showerror("Error", str(e))
                self._set_status(f"Error: {e}")

        add_btn = tk.Button(btn_frame, text="Add Patient", command=add_patient)
        add_btn.pack(side="left", padx=5)

        list_frame = tk.Frame(self.main_area, borderwidth=1, relief="solid")
        list_frame.pack(fill="both", expand=True, padx=10, pady=10)

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set)
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=listbox.yview)

        self._refresh_patients_list(listbox)

    def _refresh_patients_list(self, listbox):
        listbox.delete(0, tk.END)
        rows = self.service.patients.list_all()
        for r in rows:
            listbox.insert(
                tk.END,
                f"ID:{r[0]} | {r[1]} | Phone:{r[2]} | IC:{r[3]} | Addr:{r[4] if r[4] else '-'}",
            )

    # -------------------------
    # Doctors Page
    # -------------------------
    def _show_doctors(self):
        self._clear_main()
        header = tk.Label(self.main_area, text="Doctors", font=("Arial", 14), pady=10)
        header.pack()

        form = tk.Frame(self.main_area)
        form.pack(pady=5, fill="x")

        tk.Label(form, text="Full Name").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        tk.Label(form, text="Phone").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        tk.Label(form, text="Staff ID").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        tk.Label(form, text="Specialization").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        tk.Label(form, text="Fee (RM)").grid(row=4, column=0, sticky="w", padx=5, pady=2)

        name_entry = tk.Entry(form, width=40)
        phone_entry = tk.Entry(form, width=40)
        staff_entry = tk.Entry(form, width=40)
        spec_entry = tk.Entry(form, width=40)
        fee_entry = tk.Entry(form, width=40)

        name_entry.grid(row=0, column=1, padx=5, pady=2)
        phone_entry.grid(row=1, column=1, padx=5, pady=2)
        staff_entry.grid(row=2, column=1, padx=5, pady=2)
        spec_entry.grid(row=3, column=1, padx=5, pady=2)
        fee_entry.grid(row=4, column=1, padx=5, pady=2)

        btn_frame = tk.Frame(self.main_area)
        btn_frame.pack(pady=5)

        def add_doctor():
            try:
                did = self.service.add_doctor(
                    name_entry.get(),
                    phone_entry.get(),
                    staff_entry.get(),
                    spec_entry.get(),
                    fee_entry.get() if fee_entry.get().strip() else 0,
                )
                messagebox.showinfo("Success", f"Doctor added. ID = {did}")
                self._set_status(f"Added doctor ID {did}")
                self._refresh_doctors_list(listbox)
            except Exception as e:
                messagebox.showerror("Error", str(e))
                self._set_status(f"Error: {e}")

        add_btn = tk.Button(btn_frame, text="Add Doctor", command=add_doctor)
        add_btn.pack(side="left", padx=5)

        list_frame = tk.Frame(self.main_area, borderwidth=1, relief="solid")
        list_frame.pack(fill="both", expand=True, padx=10, pady=10)

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set)
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=listbox.yview)

        self._refresh_doctors_list(listbox)

    def _refresh_doctors_list(self, listbox):
        listbox.delete(0, tk.END)
        rows = self.service.doctors.list_all()
        for r in rows:
            listbox.insert(
                tk.END,
                f"ID:{r[0]} | {r[1]} | Phone:{r[2]} | Staff:{r[3]} | Spec:{r[4]} | Fee:RM{float(r[5]):.2f}",
            )

    # -------------------------
    # Appointments Page
    # -------------------------
    def _show_appointments(self):
        self._clear_main()
        header = tk.Label(self.main_area, text="Appointments", font=("Arial", 14), pady=10)
        header.pack()

        top = tk.Frame(self.main_area)
        top.pack(fill="x", padx=10, pady=5)

        tk.Label(top, text="Patient ID").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        tk.Label(top, text="Doctor ID").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        tk.Label(top, text="Datetime (YYYY-MM-DD HH:MM)").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        tk.Label(top, text="Reason").grid(row=3, column=0, sticky="w", padx=5, pady=2)

        patient_entry = tk.Entry(top, width=40)
        doctor_entry = tk.Entry(top, width=40)
        dt_entry = tk.Entry(top, width=40)
        reason_entry = tk.Entry(top, width=40)

        patient_entry.grid(row=0, column=1, padx=5, pady=2)
        doctor_entry.grid(row=1, column=1, padx=5, pady=2)
        dt_entry.grid(row=2, column=1, padx=5, pady=2)
        reason_entry.grid(row=3, column=1, padx=5, pady=2)

        status_frame = tk.Frame(self.main_area, borderwidth=1, relief="solid")
        status_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(status_frame, text="Change Status for Selected Appointment:").pack(anchor="w", padx=5, pady=2)

        status_var = tk.StringVar()
        status_var.set(Appointment.STATUS_CONFIRMED)

        rb1 = tk.Radiobutton(status_frame, text="CONFIRMED", variable=status_var, value=Appointment.STATUS_CONFIRMED)
        rb2 = tk.Radiobutton(status_frame, text="CANCELLED", variable=status_var, value=Appointment.STATUS_CANCELLED)
        rb3 = tk.Radiobutton(status_frame, text="COMPLETED", variable=status_var, value=Appointment.STATUS_COMPLETED)

        rb1.pack(side="left", padx=10, pady=2)
        rb2.pack(side="left", padx=10, pady=2)
        rb3.pack(side="left", padx=10, pady=2)

        action = tk.Frame(self.main_area)
        action.pack(fill="x", padx=10, pady=5)

        def book():
            try:
                aid = self.service.book_appointment(
                    int(patient_entry.get().strip()),
                    int(doctor_entry.get().strip()),
                    dt_entry.get(),
                    reason_entry.get(),
                )
                messagebox.showinfo("Success", f"Appointment booked. ID = {aid}")
                self._set_status(f"Booked appointment ID {aid}")
                self._refresh_appt_list(listbox)
            except Exception as e:
                messagebox.showerror("Error", str(e))
                self._set_status(f"Error: {e}")

        def change_status():
            try:
                appt_id = self._get_selected_appointment_id(listbox)
                self.service.change_status(appt_id, status_var.get())
                messagebox.showinfo("Success", f"Updated appointment status (ID={appt_id})")
                self._set_status(f"Updated status appointment ID {appt_id}")
                self._refresh_appt_list(listbox)
            except Exception as e:
                messagebox.showerror("Error", str(e))
                self._set_status(f"Error: {e}")

        def reschedule():
            try:
                appt_id = self._get_selected_appointment_id(listbox)
                new_dt = simple_input_dialog(self.root, "Reschedule", "Enter new datetime (YYYY-MM-DD HH:MM):")
                if new_dt is None:
                    return
                self.service.reschedule(appt_id, new_dt)
                messagebox.showinfo("Success", f"Rescheduled appointment (ID={appt_id})")
                self._set_status(f"Rescheduled appointment ID {appt_id}")
                self._refresh_appt_list(listbox)
            except Exception as e:
                messagebox.showerror("Error", str(e))
                self._set_status(f"Error: {e}")

        tk.Button(action, text="Book Appointment", command=book).pack(side="left", padx=5)
        tk.Button(action, text="Change Status", command=change_status).pack(side="left", padx=5)
        tk.Button(action, text="Reschedule", command=reschedule).pack(side="left", padx=5)

        list_frame = tk.Frame(self.main_area, borderwidth=1, relief="solid")
        list_frame.pack(fill="both", expand=True, padx=10, pady=10)

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set)
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=listbox.yview)

        self._refresh_appt_list(listbox)

        hint = tk.Label(
            self.main_area,
            text="Tip: Select an appointment in the list before changing status / reschedule.",
            pady=5,
        )
        hint.pack()

    def _refresh_appt_list(self, listbox):
        listbox.delete(0, tk.END)
        rows = self.service.appointments.list_all()
        for r in rows:
            listbox.insert(
                tk.END,
                f"ApptID:{r[0]} | {r[1]} | {r[2]} | Patient({r[4]}):{r[5]} | Doctor({r[6]}):{r[7]} | Reason:{r[3] if r[3] else '-'}",
            )

    def _get_selected_appointment_id(self, listbox):
        sel = listbox.curselection()
        if not sel:
            raise ValidationError("Please select an appointment first.")
        text = listbox.get(sel[0])
        # format starts with ApptID:xxx
        try:
            part = text.split("|")[0].strip()
            appt_id = int(part.replace("ApptID:", "").strip())
            return appt_id
        except:
            raise ValidationError("Failed to detect appointment ID from selection.")

    # -------------------------
    # Procedures/Billing Page
    # -------------------------
    def _show_procedures(self):
        self._clear_main()
        header = tk.Label(self.main_area, text="Procedures / Billing", font=("Arial", 14), pady=10)
        header.pack()

        form = tk.Frame(self.main_area)
        form.pack(fill="x", padx=10, pady=5)

        tk.Label(form, text="Patient ID").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        tk.Label(form, text="Procedure Name").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        tk.Label(form, text="Date (YYYY-MM-DD)").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        tk.Label(form, text="Practitioner").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        tk.Label(form, text="Charges (RM)").grid(row=4, column=0, sticky="w", padx=5, pady=2)

        pid_entry = tk.Entry(form, width=40)
        proc_entry = tk.Entry(form, width=40)
        date_entry = tk.Entry(form, width=40)
        prac_entry = tk.Entry(form, width=40)
        charge_entry = tk.Entry(form, width=40)

        pid_entry.grid(row=0, column=1, padx=5, pady=2)
        proc_entry.grid(row=1, column=1, padx=5, pady=2)
        date_entry.grid(row=2, column=1, padx=5, pady=2)
        prac_entry.grid(row=3, column=1, padx=5, pady=2)
        charge_entry.grid(row=4, column=1, padx=5, pady=2)

        bottom = tk.Frame(self.main_area)
        bottom.pack(fill="x", padx=10, pady=5)

        def add_proc():
            try:
                proc_id = self.service.add_procedure_for_patient(
                    int(pid_entry.get().strip()),
                    proc_entry.get(),
                    date_entry.get(),
                    prac_entry.get(),
                    charge_entry.get(),
                )
                messagebox.showinfo("Success", f"Procedure saved. ID = {proc_id}")
                self._set_status(f"Added procedure ID {proc_id}")
                self._refresh_procedure_list(listbox, int(pid_entry.get().strip()))
                self._refresh_total_label(total_var, int(pid_entry.get().strip()))
            except Exception as e:
                messagebox.showerror("Error", str(e))
                self._set_status(f"Error: {e}")

        def load_patient_procs():
            try:
                patient_id = int(pid_entry.get().strip())
                self._refresh_procedure_list(listbox, patient_id)
                self._refresh_total_label(total_var, patient_id)
                self._set_status(f"Loaded procedures for patient ID {patient_id}")
            except Exception as e:
                messagebox.showerror("Error", str(e))
                self._set_status(f"Error: {e}")

        tk.Button(bottom, text="Save Procedure", command=add_proc).pack(side="left", padx=5)
        tk.Button(bottom, text="Load Patient Procedures", command=load_patient_procs).pack(side="left", padx=5)

        total_var = tk.StringVar()
        total_var.set("Total Charges: RM0.00")
        tk.Label(bottom, textvariable=total_var).pack(side="right", padx=10)

        list_frame = tk.Frame(self.main_area, borderwidth=1, relief="solid")
        list_frame.pack(fill="both", expand=True, padx=10, pady=10)

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set)
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=listbox.yview)

    def _refresh_procedure_list(self, listbox, patient_id):
        listbox.delete(0, tk.END)
        rows = self.service.procedures.list_by_patient(patient_id)
        for r in rows:
            listbox.insert(
                tk.END,
                f"ProcID:{r[0]} | {r[1]} | {r[2]} | By:{r[3]} | RM{float(r[4]):.2f} | ApptID:{r[5] if r[5] else '-'}",
            )

    def _refresh_total_label(self, total_var, patient_id):
        total = self.service.procedures.total_charges_by_patient(patient_id)
        total_var.set(f"Total Charges: RM{total:.2f}")

    # -------------------------
    # Analytics Page (Optional libs)
    # -------------------------
    def _show_analytics(self):
        self._clear_main()
        header = tk.Label(self.main_area, text="Analytics (Optional: pandas/numpy/matplotlib/seaborn)", font=("Arial", 14), pady=10)
        header.pack()

        info = tk.Label(
            self.main_area,
            text="This page uses optional libraries from notes. If not installed, it will still show basic text summary.",
            pady=5,
        )
        info.pack()

        options = tk.Frame(self.main_area, borderwidth=1, relief="solid")
        options.pack(fill="x", padx=10, pady=10)

        export_var = tk.IntVar()
        export_var.set(0)
        chk_export = tk.Checkbutton(options, text="Export appointments to Excel (appointments.xlsx)", variable=export_var)
        chk_export.pack(side="left", padx=10, pady=5)

        heatmap_var = tk.IntVar()
        heatmap_var.set(0)
        chk_heatmap = tk.Checkbutton(options, text="Try seaborn heatmap (if available)", variable=heatmap_var)
        chk_heatmap.pack(side="left", padx=10, pady=5)

        output = tk.Text(self.main_area, height=18)
        output.pack(fill="both", expand=True, padx=10, pady=10)

        def run_analytics():
            output.delete("1.0", tk.END)
            rows = self.service.appointments.list_all()

            # basic counts
            status_counts = {}
            for r in rows:
                status_counts[r[2]] = status_counts.get(r[2], 0) + 1

            output.insert(tk.END, f"Total appointments: {len(rows)}\n")
            output.insert(tk.END, "Status breakdown:\n")
            for k in sorted(status_counts.keys()):
                output.insert(tk.END, f"  - {k}: {status_counts[k]}\n")

            try:
                import pandas as pd
                import numpy as np
                import matplotlib.pyplot as plt

                data = []
                for r in rows:
                    data.append({
                        "appointment_id": r[0],
                        "appt_datetime": r[1],
                        "status": r[2],
                        "reason": r[3],
                        "patient_id": r[4],
                        "patient_name": r[5],
                        "doctor_id": r[6],
                        "doctor_name": r[7],
                    })

                df = pd.DataFrame(data)
                if df.empty:
                    output.insert(tk.END, "\nNo data to analyze.\n")
                    return

                df["appt_datetime"] = pd.to_datetime(df["appt_datetime"])
                df["date"] = df["appt_datetime"].dt.date
                df["weekday"] = df["appt_datetime"].dt.day_name()

                if export_var.get() == 1:
                    df.to_excel("appointments.xlsx", index=False)
                    output.insert(tk.END, "\nExported: appointments.xlsx\n")

                daily = df.groupby("date")["appointment_id"].count()
                plt.figure()
                daily.plot()
                plt.title("Appointments per Day")
                plt.xlabel("Date")
                plt.ylabel("Count")
                plt.show()

                plt.figure()
                df["status"].value_counts().plot(kind="pie", autopct="%1.1f%%")
                plt.title("Appointment Status Distribution")
                plt.ylabel("")
                plt.show()

                plt.figure()
                df["hour"] = df["appt_datetime"].dt.hour
                df["hour"].plot(kind="hist")
                plt.title("Appointment Hours Distribution")
                plt.xlabel("Hour")
                plt.ylabel("Frequency")
                plt.show()

                output.insert(tk.END, "\nCharts shown using matplotlib.\n")

                if heatmap_var.get() == 1:
                    try:
                        import seaborn as sns
                        pivot = df.pivot_table(index="doctor_name", columns="weekday", values="appointment_id", aggfunc="count", fill_value=0)
                        plt.figure()
                        sns.heatmap(pivot)
                        plt.title("Doctor vs Weekday Appointment Counts")
                        plt.show()
                        output.insert(tk.END, "Seaborn heatmap shown.\n")
                    except Exception as e:
                        output.insert(tk.END, f"Seaborn heatmap failed: {e}\n")

            except Exception as e:
                output.insert(tk.END, f"\nOptional analytics not available or failed: {e}\n")
                output.insert(tk.END, "You can still use the system without these libraries.\n")

        tk.Button(self.main_area, text="Run Analytics", command=run_analytics).pack(pady=5)

    # -------------------------
    # GC Tools Page (from notes)
    # -------------------------
    def _show_gc_tools(self):
        self._clear_main()
        header = tk.Label(self.main_area, text="Garbage Collection (GC) Tools", font=("Arial", 14), pady=10)
        header.pack()

        info = tk.Label(self.main_area, text="Demo of gc module: check/enable/disable GC.", pady=5)
        info.pack()

        gc_var = tk.StringVar()
        gc_var.set(f"GC Enabled: {gc.isenabled()}")

        label = tk.Label(self.main_area, textvariable=gc_var, pady=10)
        label.pack()

        def refresh():
            gc_var.set(f"GC Enabled: {gc.isenabled()}")
            self._set_status("GC status refreshed.")

        def disable_gc():
            gc.disable()
            refresh()
            messagebox.showinfo("GC", "Garbage Collector disabled.")

        def enable_gc():
            gc.enable()
            refresh()
            messagebox.showinfo("GC", "Garbage Collector enabled.")

        btns = tk.Frame(self.main_area)
        btns.pack(pady=10)

        tk.Button(btns, text="Refresh", command=refresh).pack(side="left", padx=5)
        tk.Button(btns, text="Disable GC", command=disable_gc).pack(side="left", padx=5)
        tk.Button(btns, text="Enable GC", command=enable_gc).pack(side="left", padx=5)


# =========================
# Small helper: Input Dialog (Toplevel)
# =========================
def simple_input_dialog(parent, title, prompt):
    win = tk.Toplevel(parent)
    win.title(title)
    win.geometry("420x150")
    win.grab_set()

    tk.Label(win, text=prompt, pady=10).pack()

    entry = tk.Entry(win, width=45)
    entry.pack(pady=5)
    entry.focus_set()

    result = {"value": None}

    def ok():
        result["value"] = entry.get()
        win.destroy()

    def cancel():
        result["value"] = None
        win.destroy()

    btns = tk.Frame(win)
    btns.pack(pady=10)
    tk.Button(btns, text="OK", width=10, command=ok).pack(side="left", padx=5)
    tk.Button(btns, text="Cancel", width=10, command=cancel).pack(side="left", padx=5)

    parent.wait_window(win)
    return result["value"]


# =========================
# Run App
# =========================
if __name__ == "__main__":
    ClinicAppGUI()