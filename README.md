# Student Fee Management System

A full-stack web application designed to streamline tuition billing, registration proof tracking, bursary allocations, and payment processing within higher education institutions, while proactively evaluating student debt risk[cite: 8, 20].

## Programme & Institution
* **Institution:** Sol Plaatje University
* **Department:** Computer Science & Information Technology
* **Programme:** Advanced Diploma in ICT (Applications Development)
* **Module:** NPRJ740 – Project
* **Author:** Wanda Giqo (Student Number: 202213951)


---

## Key Features
* **Role-Based Access Control (RBAC):** Secure authentication separating Student self-service portals from Staff, Finance, and HR administrative dashboards.
* **Academic Year Enrollment Tracking:** Organizes fee structures, student profiles, and ledger balances per academic year.
* **Itemized Fee Management & Calculation:** Automatically computes net outstanding balances ($\text{Total Fees} - (\text{Payments} + \text{Bursaries})$).
* **Auditable Payment Workflow:** Enables students to upload proof-of-payment documents while enforcing a mandatory staff verification queue (`Pending` $\rightarrow$ `Approved`) before ledger updates.
* **Predictive Debt Risk Engine:** Evaluates balance ratios and payment histories in real-time to categorize students into **Low**, **Medium**, or **High Risk** profiles to prevent unexpected financial exclusion.

---

## Technology Stack
* **Backend Framework:** Python 3.10+, Django 4.2+ (Model-View-Template Architecture)
* **Frontend Interface:** HTML5, Bootstrap 5.3, CSS3, JavaScript, Bootstrap Icons
* **Database Layer:** PostgreSQL / MySQL Relational Database via Django ORM
* **Environment Management:** Local WSGI runtime with modular service logic (`services.py`)

---

## Project Structure
```text
student_fee_project/
├── manage.py                          # Django CLI utility
├── student_fee_project/               # Core configuration directory
│   ├── settings.py                    # Environment settings & DB configuration
│   ├── urls.py                        # Master URL routing
│   └── wsgi.py                        # Application server gateway
└── fees_app/                          # Main application module
    ├── models.py                      # Data models (User, StudentProfile, Payment, Fee)
    ├── views.py                       # Business logic & request handlers
    ├── forms.py                       # Student & Staff input validation forms
    ├── urls.py                        # App-level routing
    ├── services.py                    # Debt risk calculation engine
    └── templates/                     # HTML UI templates
        ├── base.html                  # Master layout with dynamic sidebar
        ├── dashboard.html             # Student dashboard view
        ├── make_payment.html          # Payment submission interface
        └── admin_dashboard.html       # Executive administrative panel
