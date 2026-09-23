# User & Administrator Manual
## NS Learnytics - Cloud-Based Academic Analytics and Class Management Platform

**Document Version:** 1.0.0  
**Target Release:** Production Release 1.0  
**Date:** September 2026  
**Audience:** System Administrators, Instructors, Academic Clerks, Students, and Parents  
**Institution:** University of Moratuwa (UOM) Supplementary Education Initiative  

---

### Table of Contents
1. [Introduction and System Overview](#1-introduction-and-system-overview)
   - 1.1 Purpose of this Manual
   - 1.2 System Architecture & Role Privileges
   - 1.3 Accessing the Platform and Browser Requirements
   - 1.4 Public Landing Page and Navigation Switcher
2. [Authentication and Account Setup](#2-authentication-and-account-setup)
   - 2.1 Public Self-Service Registration (Students & Parents)
   - 2.2 System Login and Session Security
   - 2.3 Profile Configuration and Password Management
3. [Super Administrator Guide](#3-super-administrator-guide)
   - 3.1 Administrator Analytics Dashboard
   - 3.2 Provisioning Staff Accounts (Teachers and Clerks)
   - 3.3 Provisioning Direct Parent and Student Accounts
   - 3.4 Auditing and Approving Parent-Student Link Requests
   - 3.5 User Lifecycle Management and Cascade Account Deletion
4. [Teacher & Instructor Operations Guide](#4-teacher--instructor-operations-guide)
   - 4.1 Teacher Executive Dashboard Overview
   - 4.2 Class Creation, Timetables, and Join Code Distribution
   - 4.3 Student Roster Management and Class Dropping
   - 4.4 Dual-Mode Attendance Tracking (Camera Scanning & Manual Search)
   - 4.5 Assessment Mark Entry and Class Grade Spread Distribution
   - 4.6 Generating Attendance and Performance Exports (Excel & PDF)
   - 4.7 LMS Course Materials Sharing
   - 4.8 Assignment Publication, Student Submissions, and Grading
   - 4.9 Teacher Expense Logging and Net Operating Income
   - 4.10 Publishing Targeted Course Announcements
   - 4.11 Direct Messaging with Verified Parents
5. [Front-Desk Clerk / Moderator Operations Guide](#5-front-desk-clerk--moderator-operations-guide)
   - 5.1 Front-Desk Check-in Console Interface
   - 5.2 Real-Time Optical Camera QR Attendance Scanning
   - 5.3 Manual Fallback Check-in Procedure
   - 5.4 High-Throughput Tuition Fee Collection
   - 5.5 Duplicate Payment Protection Protocols
   - 5.6 Printing Official Payment Counter Receipts
6. [Student Academic Portal Guide](#6-student-academic-portal-guide)
   - 6.1 Student Personal Dashboard
   - 6.2 Enrolling in Courses via 6-Character Join Codes
   - 6.3 Accessing and Printing the Digital QR Identity Card
   - 6.4 Downloading LMS Course Materials
   - 6.5 Submitting Homework Assignments Online
   - 6.6 Monitoring Academic Performance and Score Trajectories
   - 6.7 Student of the Month Honor Roll Recognition
7. [Parent & Guardian Monitoring Guide](#7-parent--guardian-monitoring-guide)
   - 7.1 Linking Your Account to Enrolled Children
   - 7.2 Multi-Ward Switching Dashboard
   - 7.3 Real-Time Attendance Inspection
   - 7.4 Historical Assessment Performance Tracking
   - 7.5 Accessing and Printing Official Academic Progress Reports
   - 7.6 Communicating with Teachers via Direct Messaging
8. [Intelligent Predictive Analytics Guide](#8-intelligent-predictive-analytics-guide)
   - 8.1 Understanding the AI Risk Radar (Dropout Prediction)
   - 8.2 Interpreting Risk Tiers and Diagnostic Factors
   - 8.3 Understanding the AI Grade Forecaster (Linear Regression)
   - 8.4 Interpreting Score Trajectories and Letter Grade Projections
   - 8.5 Student of the Month Evaluation Metrics and Tie-Breaking
9. [Troubleshooting, Security & Frequently Asked Questions](#9-troubleshooting-security--frequently-asked-questions)
   - 9.1 Camera Access and QR Scanning Issues
   - 9.2 Duplicate Payment Error Handling
   - 9.3 Parent Link Status Inquiries
   - 9.4 Print Formatting Optimization
   - 9.5 Session Expiry and Authentication Recovery

---

### 1. Introduction and System Overview

#### 1.1 Purpose of this Manual
This manual provides a definitive, operational reference for all stakeholders interacting with the **NS Learnytics** platform. It details end-to-end operational procedures, screen interactions, input validations, security boundaries, and predictive analytics interpretation across all five authorized user roles.

#### 1.2 System Architecture & Role Privileges
NS Learnytics structures operational authority into five discrete tiers:

| Role Identifier | System Designation | Scope of Operational Authority |
| :--- | :--- | :--- |
| `superadmin` | Super Administrator | Institutional governance, staff provisioning, parent-student link verification auditing, revenue auditing, and user lifecycle management. |
| `teacher` | Instructor / Faculty | Course creation, schedule definition, attendance verification, exam mark entry, homework grading, expense logging, risk radar analysis, and parent communication. |
| `moderator` | Front-Desk Clerk | High-volume optical QR gate check-in, manual attendance entry, cash tuition fee collection with duplicate barriers, and counter receipt issuance. |
| `student` | Student Learner | Class self-enrollment via join code, digital QR identity badge generation, lecture resource downloads, assignment submissions, and grade tracking. |
| `parent` | Parent / Guardian | Ward linkage requests, multi-child monitoring, attendance checking, test score review, official printable progress report cards, and teacher messaging. |

#### 1.3 Accessing the Platform and Browser Requirements
- **Web Address:** Access the platform URL provided by your institution (e.g., `http://localhost:5000` for on-premises servers or the institutional domain).
- **Supported Browsers:** Google Chrome (v90+), Mozilla Firefox (v88+), Apple Safari (v14+), and Microsoft Edge (v90+).
- **Hardware Prerequisites:** Devices performing QR gate check-in must have a front-facing or rear optical camera with browser permissions granted. Standard webcams and USB handheld 2D laser barcode scanners (HID mode) are natively supported.

#### 1.4 Public Landing Page and Navigation Switcher
When visiting the root domain (`/`), users are presented with the public landing page.
- **Header Toggle Switch:** The top navigation bar features a segmented control toggle allowing immediate switching between the **Login** form and the **Get Started (Register)** form.
- The active tab is visually emphasized with high-contrast styling, ensuring users always know which state they are viewing.

---

### 2. Authentication and Account Setup

#### 2.1 Public Self-Service Registration (Students & Parents)
Prospective students and guardians can establish their accounts independently:
1. Navigate to the public landing page and select **Get Started** on the segmented toggle switch.
2. Complete the registration form:
   - **Full Name:** Enter your official legal name.
   - **Email Address:** Enter a valid, accessible email (must be globally unique).
   - **Password:** Enter a strong password (minimum 8 characters recommended).
   - **Account Type:** Select either `student` or `parent`.
3. Submit the form by clicking **Create Account**.
4. *Automated Background Action for Students:* The platform automatically initializes a student profile and generates an encrypted 64-character hexadecimal QR token.

#### 2.2 System Login and Session Security
1. Select **Login** on the header toggle switch.
2. Enter your registered email address and password.
3. Click **Sign In**.
4. The system validates the credentials against PBKDF2 cryptographic hashes stored in the database.
5. Upon successful verification, you are automatically directed to your role-specific dashboard:
   - Super Administrator: `/admin/dashboard`
   - Teacher: `/classes/teacher_dashboard`
   - Clerk: `/attendance/clerk_dashboard`
   - Student: `/classes/student_dashboard`
   - Parent: `/parent/dashboard`
6. *Session Termination:* To log out securely, click **Sign Out** in the upper-right user navigation menu. Always terminate sessions when using shared campus terminals.

#### 2.3 Profile Configuration and Password Management
All authenticated users can update their profile information:
1. Click your name or profile avatar in the navigation bar and select **Edit Profile** (`/profile/edit`).
2. Update contact details, student grade levels, or teacher subject competencies and professional experience.
3. Click **Save Changes** to commit updates.

---

### 3. Super Administrator Guide

#### 3.1 Administrator Analytics Dashboard
The Super Admin dashboard (`/admin/dashboard`) acts as the command center for institutional leadership.
- **Top Metric Cards:**
  - *Total Students Enrolled:* Active student count across all classes.
  - *Staff Members:* Count of active instructors and front-desk clerks.
  - *Total Revenue:* Gross cumulative tuition fees collected across the institution.
  - *Pending Parent Requests:* Linkage requests awaiting administrative review.
  - *Active Classes:* Current active course sections.
- **Recent Registrations:** Displays the five most recent user signups with role tags and timestamps.

#### 3.2 Provisioning Staff Accounts (Teachers and Clerks)
Super Administrators possess exclusive authority to create staff credentials:
1. On the Admin Dashboard, locate the **Create Staff Account** card.
2. Enter the staff member's **Full Name**, **Email Address**, and temporary **Password**.
3. Select the appropriate **Role**:
   - `teacher`: Grants instructional and grading authority.
   - `moderator`: Grants front-desk attendance and tuition cashier privileges.
4. Click **Create Staff Account**. The system provisions the account immediately and initializes the corresponding profile table.

#### 3.3 Provisioning Direct Parent and Student Accounts
Administrators can pre-configure accounts directly:
- **Direct Student Creation:** Enter name, email, password, and academic grade. The system provisions the account, hashes credentials, and issues a unique QR token.
- **Direct Parent Creation with Instant Linkage:** Enter parent name, email, password, and optionally specify a target Student ID. When a Student ID is supplied, the relationship is established immediately with `approved` status, bypassing the pending queue.

#### 3.4 Auditing and Approving Parent-Student Link Requests
To protect student privacy, parent self-service linkage requests require administrative verification:
1. Navigate to **Parent Requests** via the sidebar or top alert badge (`/admin/parent-requests`).
2. The **Pending Requests** table displays:
   - Parent Name & Email
   - Target Student Name & Email
   - Request Submission Timestamp
3. Cross-reference the parent's identity against physical institutional admission records.
4. Click **Approve** to activate the parent's monitoring access, or **Reject** to deny the request.
5. Historical verification actions are logged in the **Resolution History** table below.

#### 3.5 User Lifecycle Management and Cascade Account Deletion
To maintain data hygiene and handle departures:
1. Navigate to **Manage Users** (`/admin/manage-users`).
2. The interface categorizes accounts into **Staff Members** and **Enrolled Students**.
3. To remove an account, locate the user row and click **Delete User**.
4. *Safety Guard:* The platform prohibits an administrator from deleting their own active session account.
5. *Cascade Integrity:* The platform executes a transactional cascade delete, purging all linked profiles, course enrollments, attendance marks, test scores, and parent connections cleanly from the database.

---

### 4. Teacher & Instructor Operations Guide

#### 4.1 Teacher Executive Dashboard Overview
The Teacher Dashboard (`/classes/teacher_dashboard`) synthesizes instructional operations:
- **Metrics Bar:** Active Classes, Total Enrolled Students, Gross Fee Earnings, and Today's Date.
- **Today's Schedule Widget:** Dynamically identifies and highlights classes scheduled for the current day of the week, displaying class title, timetable hours, and enrollment count.
- **Grade Spread Widget:** Displays an aggregate distribution curve illustrating student mark distributions across all classes taught by the instructor.
- **Student of the Month Banner:** Highlights the top-performing students across the instructor's subjects for the current month.

#### 4.2 Class Creation, Timetables, and Join Code Distribution
To launch a new course section:
1. Click **Create New Class** on the dashboard.
2. In the modal dialog, specify:
   - **Subject Name:** (e.g., "Advanced Level Physics", "Combined Mathematics").
   - **Weekly Schedule:** (e.g., "Saturday 08:00 AM - 11:30 AM").
   - **Monthly Tuition Fee:** Numerical value in institutional currency (e.g., `3500.00`).
3. Click **Create Class**.
4. The system initializes the class record and generates a unique 6-character alphanumeric join key (e.g., `PHY802`).
5. Share this join key with students during orientation for self-enrollment.

#### 4.3 Student Roster Management and Class Dropping
1. In the **My Classes** section of the dashboard, click **Manage Class** on the relevant course card.
2. The **Enrolled Students** table lists all enrolled learners, their academic grade, and their enrollment date.
3. *Dropping Students:* To unenroll an inactive or withdrawn student, click **Drop Student** on their row. The system removes the enrollment mapping while retaining historical attendance and marks records for auditing.

#### 4.4 Dual-Mode Attendance Tracking (Camera Scanning & Manual Search)
Instructors can mark attendance directly in the classroom:
1. On the class overview, click **Take Attendance** (`/attendance/mark/<class_id>`).
2. **Mode 1 - Optical QR Scanner:**
   - Click **Start Camera Scanner**.
   - Direct the student's physical or digital QR card toward the camera.
   - The scanner decodes the 64-character token and immediately sends a check-in request.
   - A green confirmation banner indicates success, displaying student name and check-in time.
3. **Mode 2 - Manual Search Fallback:**
   - If a student cannot present their card, enter their name or student ID in the manual search box.
   - Click **Mark Present**.
4. *Daily Duplication Guard:* Scanning a student repeatedly on the same day updates the existing record without creating duplicate entries.

#### 4.5 Assessment Mark Entry and Class Grade Spread Distribution
1. Navigate to **Performance** and select **Record Test Marks** (`/performance/record_marks/<class_id>`).
2. Input the general assessment parameters:
   - **Test Name:** (e.g., "Monthly Revision Exam 01", "Thermodynamics Unit Quiz").
   - **Maximum Marks:** Default is 100.0.
   - **Date Administered:** Select the examination date.
3. Enter the marks obtained for each student in the roster list.
4. Click **Save Marks**.
5. The system computes percentage scores, class averages, standard deviation, and updates the **Class Grade Spread** Chart.js histogram.

#### 4.6 Generating Attendance and Performance Exports (Excel & PDF)
To produce archival documentation for department meetings:
- **Attendance Register Export:** Click **Export Attendance** (`/attendance/export/<class_id>`). Choose **Excel (.xlsx)** for an editable spreadsheet or **PDF Document** for a formal printable sheet.
- **Performance Ledger Export:** Click **Export Performance** (`/performance/export/<class_id>`). Download structured mark books including student names, scores, percentages, and class averages.

#### 4.7 LMS Course Materials Sharing
1. In the class console, navigate to the **Learning Materials** tab (`/lms/class/<class_id>`).
2. Click **Upload Material**.
3. Enter the **Title** and **Description** (e.g., "Vectors Lecture Notes & Problem Sheet").
4. Attach the resource file (PDF, DOCX, PPTX, or ZIP up to 50MB).
5. Click **Upload**. Enrolled students and linked parents gain immediate access to download the file.

#### 4.8 Assignment Publication, Student Submissions, and Grading
1. On the LMS tab, click **Create Assignment**.
2. Specify the **Assignment Title**, **Instructions**, **Due Date & Time**, and **Maximum Points**.
3. Optionally attach a supplementary question sheet.
4. Click **Publish Assignment**.
5. *Grading Submissions:* Click **View Submissions** on the assignment card. Inspect submitted text and student attachments, enter numerical marks awarded, type qualitative feedback remarks, and click **Submit Grade**. The submission status updates from `submitted` to `graded`.

#### 4.9 Teacher Expense Logging and Net Operating Income
Instructors can monitor their financial health:
1. Navigate to the **Financials & Expenses** tab (`/finance/teacher_income`).
2. The summary cards display **Gross Tuition Revenue Collected**, **Total Operating Expenses**, and **Net Teaching Income**.
3. To log an operational expense (e.g., hall rental, photocopying test papers, laboratory consumables), enter the **Description**, **Amount**, and **Date**, then click **Log Expense**.
4. The system recalculates net operating income in real time.

#### 4.10 Publishing Targeted Course Announcements
1. Navigate to **Announcements** on the teacher dashboard (`/announcements/create`).
2. Select the target class.
3. Enter the **Title** and **Announcement Content**.
4. Select the **Target Audience**:
   - `all`: Visible to both enrolled students and their linked parents.
   - `students_only`: Visible exclusively in student portals.
   - `parents_only`: Visible exclusively in parent monitoring consoles.
5. Click **Publish Announcement**.

#### 4.11 Direct Messaging with Verified Parents
1. Click **Messages** in the primary navigation menu (`/messages/`).
2. Select an active conversation or start a new thread by selecting a verified parent linked to one of your students.
3. Type your message and click **Send**.
4. The interface tracks delivery and read receipts (`is_read`), displaying unread badges when incoming parent queries arrive.

---

### 5. Front-Desk Clerk / Moderator Operations Guide

#### 5.1 Front-Desk Check-in Console Interface
The Clerk portal (`/attendance/clerk_dashboard`) is tailored for high-throughput morning operations:
- Split-screen layout optimized for rapid dual-mode gate attendance verification and cash tuition intake.
- Real-time attendance feed listing the last 20 verified students with timestamps.

#### 5.2 Real-Time Optical Camera QR Attendance Scanning
1. Position the terminal webcam or USB barcode reader at the entrance desk.
2. Select the active class session from the dropdown menu.
3. Click **Activate Optical Scanner**.
4. As students pass through the gate, have them present their physical badge or mobile screen to the camera.
5. The scanner reads the 64-character token within 150 milliseconds.
6. A green confirmation banner displays:
   - Student Name
   - Enrolled Class
   - Recorded Timestamp
   - Optional: Monthly Fee Payment Status Badge (e.g., "Paid" or "Fee Due")

#### 5.3 Manual Fallback Check-in Procedure
If a student's card is damaged, wet, or their smartphone battery is depleted:
1. Switch to the **Manual Check-in** panel on the console.
2. Type the student's name, email, or Student ID in the search input.
3. Select the verified student record from the instant autocomplete list.
4. Click **Confirm Check-in**.

#### 5.4 High-Throughput Tuition Fee Collection
1. On the Clerk Console, locate the **Collect Tuition Fee** panel (`/finance/clerk_collect_fee`).
2. Select the **Class** and search for the **Student**.
3. Select the **Billing Period** in `YYYY-MM` format (e.g., `2026-09`).
4. The system automatically populates the standard monthly class fee.
5. Collect physical cash or confirm transfer.
6. Click **Confirm Payment & Issue Receipt**.

#### 5.5 Duplicate Payment Protection Protocols
The platform employs automated barriers to prevent double-billing:
- *Dynamic AJAX Pre-Check:* As soon as the student, class, and period are selected, the system checks the database. If a payment record already exists for that period, a yellow warning banner appears:
  `Warning: Student has already paid for this billing period.`
  The **Confirm Payment** button is automatically disabled.
- *Server-Side Barrier:* Even if two clerks attempt to record payments simultaneously, the server rejects the second submission with an `HTTP 409 Conflict` error, backed by the database constraint `UNIQUE KEY unique_class_student_period`.

#### 5.6 Printing Official Payment Counter Receipts
1. Immediately upon successful fee registration, a modal dialog presents the transaction confirmation.
2. Click **Print Official Receipt** (`/finance/receipt/<payment_id>`).
3. The browser print dialog opens with a pre-formatted counter receipt containing:
   - Receipt Number and Transaction Timestamp
   - Student Full Name and Enrolled Class
   - Billing Month Period and Total Amount Paid
   - Cashier / Clerk Identification
4. Print the slip on standard 80mm POS thermal paper or A5 paper for the parent or student.

---

### 6. Student Academic Portal Guide

#### 6.1 Student Personal Dashboard
The Student Dashboard (`/classes/student_dashboard`) presents an integrated personal overview:
- **Summary Cards:** Total Enrolled Classes, Overall Attendance Percentage, Assessments Completed, and Total Fees Paid.
- **Student of the Month Honor Card:** Prominently highlights the top achievers across your subjects.
- **My Classes Grid:** Quick-action cards for enrolled subjects with links to course materials, homework tasks, and exam history.

#### 6.2 Enrolling in Courses via 6-Character Join Codes
1. Obtain the 6-character alphanumeric join code from your instructor (e.g., `MAT401`).
2. On your dashboard, click **Join New Class** (`/enrollment/join`).
3. Enter the code in the input field and click **Enroll**.
4. The system validates the code and adds the course to your dashboard immediately. If you enter an invalid code or are already enrolled, a clear notification will explain the issue.

#### 6.3 Accessing and Printing the Digital QR Identity Card
1. Click **My QR Card** in the primary navigation bar (`/attendance/my_qr`).
2. The screen renders your personalized digital identification badge containing:
   - High-resolution dynamic QR code representing your 64-character security token.
   - Student Full Name, Registered Email, and Academic Grade.
3. *Mobile Usage:* Present this screen on your smartphone at the entrance desk for instant check-in.
4. *Physical Card Printing:* Click **Print Physical Badge** to output a wallet-sized card on heavy paper or cardstock.

#### 6.4 Downloading LMS Course Materials
1. Select the relevant course card and click **Course Materials** (`/lms/class/<class_id>`).
2. Browse published lecture notes, syllabus guides, and problem sets.
3. Click **Download Asset** to save the file to your device.

#### 6.5 Submitting Homework Assignments Online
1. In the course console, navigate to the **Assignments** section.
2. Locate the active task and review the instructions and due date.
3. Click **Submit Solution** (`/lms/submit_assignment/<assignment_id>`).
4. Type your written response in the text area and/or attach your solution file (PDF, DOCX, ZIP, or image).
5. Click **Upload & Submit**.
6. The interface confirms submission with a timestamp and locks the entry against accidental double-submissions. Once graded by the instructor, your score and teacher feedback remarks will appear here.

#### 6.6 Monitoring Academic Performance and Score Trajectories
1. Click **Performance Analytics** on your dashboard.
2. Review the chronological breakdown of all recorded examination marks.
3. Review your **AI Grade Forecaster** cards for each subject:
   - *Current Average & Grade:* Computed across historical evaluations.
   - *Predicted Next-Exam Score:* Algorithmic forecast of your upcoming mark.
   - *Trajectory Indicator:* Displays whether your performance is *Improving*, *Declining*, or *Stable*.

#### 6.7 Student of the Month Honor Roll Recognition
If you achieve the highest average score in a subject during a calendar month, your name and academic grade will be featured in the **Student of the Month** showcase across all student and faculty dashboards.

---

### 7. Parent & Guardian Monitoring Guide

#### 7.1 Linking Your Account to Enrolled Children
To monitor your child's attendance and academic progress, you must establish a verified link:
1. Register a Parent account via the public registration switcher.
2. On your parent dashboard, locate the **Link a Student** panel (`/parent/request_link`).
3. Enter the exact **Registered Email Address** of your child.
4. Click **Submit Link Request**.
5. The request enters `pending` status. Once the Super Administrator verifies the family relationship against institutional records, the link updates to `approved`, and your child's data becomes accessible.

#### 7.2 Multi-Ward Switching Dashboard
If you have multiple children enrolled in the institution:
1. Access the Parent Dashboard (`/parent/dashboard`).
2. The top bar presents child selector tabs (e.g., "John Doe (Grade 11)", "Emily Doe (Grade 9)").
3. Click any child's tab to switch the entire dashboard context to their specific records.

#### 7.3 Real-Time Attendance Inspection
- The **Attendance Overview** card displays lifetime attendance percentage and recent consistency.
- Inspect the **Attendance Session Log** to review exact dates and check-in statuses (`Present` or `Absent`).
- Use this log to verify that your child arrived safely at the tutoring facility.

#### 7.4 Historical Assessment Performance Tracking
- The **Academic Mark Book** displays every examination administered to your child.
- Review the test title, date recorded, marks obtained, maximum possible marks, and calculated percentage score.
- Review the class average benchmark alongside your child's mark to evaluate relative performance.

#### 7.5 Accessing and Printing Official Academic Progress Reports
1. Locate the **Progress Report** item in the persistent left navigation sidebar (`/parent/progress_report/<student_id>`).
2. The screen renders a consolidated academic report containing:
   - Student and Guardian Identification Metadata.
   - Overall Attendance Record and Attendance Rate.
   - Subject-by-Subject Examination Marks Breakdown.
   - AI Trajectory Projections and Teacher Qualitative Notes.
3. *Printing the Report:* Click **Print Progress Report** or press `Ctrl + P` (`Cmd + P` on macOS).
4. The application triggers print styling (`@media print`), stripping away navigation menus, sidebars, buttons, and dark background colors to produce a clean, formal document suitable for physical filing or submission to regular day schools.

#### 7.6 Communicating with Teachers via Direct Messaging
1. Click **Messages** in the parent navigation menu (`/messages/`).
2. Select the instructor responsible for your child's subject.
3. Send private messages to inquire about academic performance, attendance concerns, or classroom behavior.
4. Receive direct responses from instructors with unread notification indicators.

---

### 8. Intelligent Predictive Analytics Guide

#### 8.1 Understanding the AI Risk Radar (Dropout Prediction)
The **AI Risk Radar** is an early warning system designed to detect students at risk of academic failure or course dropout before major examinations occur.
- **Location:** Accessible to Instructors and Administrators via `/ai/risk_radar`.
- **Underlying Engine:** An ensemble Random Forest Classifier evaluating five core behavioral indicators:
  1. Lifetime Attendance Percentage
  2. Recent 30-Day Attendance Consistency
  3. Average Assessment Mark Percentage
  4. Longitudinal Performance Trend (delta between recent and early scores)
  5. LMS Homework Completion Ratio

#### 8.2 Interpreting Risk Tiers and Diagnostic Factors
The system categorizes each evaluated student into one of three risk tiers:

| Risk Tier | Visual Indicator | Criteria and Trigger Conditions | Recommended Pedagogical Action |
| :--- | :--- | :--- | :--- |
| **HIGH RISK** | Red Badge | Risk Score $\ge 55\%$, or Lifetime Attendance $< 55\%$, or Exam Average $< 45\%$. | Immediate one-on-one intervention; contact parents via direct messaging; schedule remedial tutoring. |
| **MEDIUM RISK** | Amber Badge | Risk Score $25\% - 54.9\%$, or Attendance $< 75\%$, or Exam Average $< 60\%$. | Monitor upcoming test scores closely; assign peer mentor; verify homework submission regularity. |
| **LOW RISK** | Green Badge | Risk Score $< 25\%$ with satisfactory attendance and consistent passing grades. | Encourage continued performance; consider for Student of the Month recognition. |

*Diagnostic Factors:* Each high or medium risk card includes natural language bullet points detailing the specific root causes (e.g., *"Critical overall attendance (48.2%)"*, *"Declining score trend (-14.0% trajectory)"*, *"Missed 50% of LMS homework"*).

#### 8.3 Understanding the AI Grade Forecaster (Linear Regression)
The **AI Grade Forecaster** models continuous score progressions over time.
- **Location:** Available across Teacher dashboards, Student portals, and Parent Progress Reports.
- **Underlying Engine:** Ordinary Least Squares (OLS) Linear Regression ($y = mx + c$) fitting a trend line through the student's chronological examination and homework scores.

#### 8.4 Interpreting Score Trajectories and Letter Grade Projections
The forecaster generates three key metrics for each course:
1. **Predicted Next-Exam Score:** Expected percentage score on the impending evaluation, bounded within $[0.0\%, 100.0\%]$.
2. **Predicted Final Grade:** Standardized letter grade mapping:
   - **Grade A:** $\ge 85.0\%$
   - **Grade B:** $75.0\% - 84.9\%$
   - **Grade C:** $65.0\% - 74.9\%$
   - **Grade S (Pass):** $50.0\% - 64.9\%$
   - **Grade F (Fail):** $< 50.0\%$
3. **Trajectory Status (Slope $m$):**
   - *Improving Trajectory ($m > +1.5$):* Upward performance trend across successive evaluations.
   - *Declining Trajectory ($m < -1.5$):* Downward performance trend; signals emerging conceptual difficulties.
   - *Stable Performance ($-1.5 \le m \le +1.5$):* Consistent score pattern.

#### 8.5 Student of the Month Evaluation Metrics and Tie-Breaking
The platform automatically evaluates and celebrates monthly top achievers:
- **Evaluation Criteria:** Computed per subject as the highest average test score during the calendar month:
  $$\text{Average Score} = \text{AVG}\left(\frac{\text{marks\_obtained}}{\text{max\_marks}} \times 100\right)$$
- **Tie-Breaking Rule:** If two or more students achieve identical percentage averages, the system awards the honor to the student who completed the higher count of tests.
- **Fallback Resolution:** If a new month has commenced and no tests have yet been recorded, the system automatically falls back to the most recent historical month with recorded marks.

---

### 9. Troubleshooting, Security & Frequently Asked Questions

#### 9.1 Camera Access and QR Scanning Issues
- **Symptom:** Optical camera scanner displays a black viewport or error: `Camera permission denied`.
- **Resolution:**
  1. In the browser address bar, click the **Padlock / Site Settings** icon.
  2. Locate **Camera** and set permission to **Allow**.
  3. Refresh the page (`F5` or `Ctrl + R`).
  4. Ensure no other application (e.g., Zoom, Teams, Skype) is actively occupying the camera device.

#### 9.2 Duplicate Payment Error Handling
- **Symptom:** The cashier interface displays: `HTTP 409 Conflict: Payment already recorded for this billing period`.
- **Resolution:** The student has already paid tuition fees for the selected month. Navigate to **Payment History** on the finance menu, enter the Student ID, and verify the existing transaction. If a duplicate receipt is required, click **Re-Print Receipt**.

#### 9.3 Parent Link Status Inquiries
- **Symptom:** Parent dashboard displays: `Pending Administrative Verification`.
- **Resolution:** The link request is in the administrative queue. Contact the institutional administrator or front-desk clerk with proof of guardianship (e.g., matching phone numbers or student birth certificate) to have the request approved via `/admin/parent-requests`.

#### 9.4 Print Formatting Optimization
- **Symptom:** Printing a progress report or receipt includes browser headers, footers (dates/URLs), or distorted margins.
- **Resolution:**
  1. In the browser Print Dialog, expand **More Settings**.
  2. Uncheck **Headers and Footers**.
  3. Ensure **Margins** are set to **Default** or **None**.
  4. Enable **Background Graphics** if watermark logos are desired.

#### 9.5 Session Expiry and Authentication Recovery
- **Symptom:** You are unexpectedly redirected to the login page with a `Session Expired` notification.
- **Resolution:** To protect institutional data, sessions automatically expire after periods of inactivity. Re-enter your credentials to resume your session. If you forget your password, contact the Super Administrator to have your credential hash reset securely.

---

*End of User & Administrator Manual.*
