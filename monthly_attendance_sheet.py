
# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from frappe.utils import cstr, cint, getdate
from frappe import msgprint, _
from calendar import monthrange
from datetime import date, timedelta
import datetime


def execute(filters=None):
	if not filters: filters = {}
	filters["total_days_in_month"]= []
	conditions, filters = get_conditions(filters)
	columns = get_columns(filters)
	att_map = get_attendance_list(conditions, filters)
	msgprint(_(att_map))

	emp_map = get_employee_details()

	holiday_list = [emp_map[d]["holiday_list"]
	    for d in emp_map if emp_map[d]["holiday_list"]]
	default_holiday_list = frappe.get_cached_value(
	    'Company',  filters.get("company"),  "default_holiday_list")
	holiday_list.append(default_holiday_list)
	holiday_list = list(set(holiday_list))
	holiday_map = get_holiday(holiday_list, filters["fromdate"],filters["todate"])

	data = []
	leave_types = frappe.db.sql(
	    """select name from `tabLeave Type`""", as_list=True)
	leave_list = [d[0] for d in leave_types]
	columns.extend(leave_list)
	# columns.extend([_("Total Late Entries") + ":Float:120",
	#                _("Total Early Exits") + ":Float:120"])

	for emp in sorted(att_map):
		emp_det = emp_map.get(emp)
		if not emp_det:
			continue

		row = [emp, emp_det.employee_name, emp_det.branch, emp_det.department, emp_det.designation,
			emp_det.company]

		total_p = total_a = total_l = 0.0
		for day in filters["total_days_in_month"]:
			status = att_map.get(emp).get(day, "None")
			status_map = {"Present": "P", "Absent": "A", "Half Day": "HD",
			    "On Leave": "L", "None": "", "Holiday": "<b>H</b>"}
			if status == "None" and holiday_map:
				emp_holiday_list = emp_det.holiday_list if emp_det.holiday_list else default_holiday_list
				if emp_holiday_list in holiday_map and (day) in holiday_map[emp_holiday_list]:
					status = "Holiday"
			row.append(status_map[status])

			if status == "Present":
				total_p += 1
			elif status == "Absent":
				total_a += 1
			elif status == "On Leave":
				total_l += 1
			elif status == "Half Day":
				total_p += 0.5
				total_a += 0.5
				total_l += 0.5

		row += [total_p, total_l, total_a]

		if not filters.get("employee"):
			filters.update({"employee": emp})
			conditions += " and employee = %(employee)s"
		elif not filters.get("employee") == emp:
			filters.update({"employee": emp})

		leave_details = frappe.db.sql("""select leave_type, status, count(*) as count from `tabAttendance`\
			where leave_type is not NULL %s group by leave_type, status""" % conditions, filters, as_dict=1)

		# time_default_counts = frappe.db.sql("""select (select count(*) from `tabAttendance` where \
		# 	late_entry = 1 %s) as late_entry_count, (select count(*) from tabAttendance where \
		# 	early_exit = 1 %s) as early_exit_count""" % (conditions, conditions), filters)

		leaves = {}
		for d in leave_details:
			if d.status == "Half Day":
				d.count = d.count * 0.5
			if d.leave_type in leaves:
				leaves[d.leave_type] += d.count
			else:
				leaves[d.leave_type] = d.count

		for d in leave_list:
			if d in leaves:
				row.append(leaves[d])
			else:
				row.append("0.0")

		# row.extend([time_default_counts[0][0], time_default_counts[0][1]])
		data.append(row)
	return columns, data


def get_columns(filters):
	columns = [
		_("Employee") + ":Link/Employee:120", _("Employee Name") +
		  "::140", _("Branch") + ":Link/Branch:120",
		_("Department") + ":Link/Department:120", _("Designation") +
		  ":Link/Designation:120",
		 _("Company") + ":Link/Company:120"
	]

	for day in filters["total_days_in_month"]:
		columns.append(cstr(day) + "::20")

	columns += [_("Total Present") + ":Float:80", _("Total Leaves") +
	              ":Float:80",  _("Total Absent") + ":Float:80"]
	return columns


def get_attendance_list(conditions, filters):
	attendance_list = frappe.db.sql("""select employee, attendance_date as day_of_month,
		status from tabAttendance where docstatus = 1 %s order by employee, attendance_date""" %
		conditions, filters, as_dict=1)

	att_map = {}
	for d in attendance_list:
		att_map.setdefault(d.employee, frappe._dict()).setdefault(d.day_of_month, "")

		att_map[d.employee][d.day_of_month] = d.status
       
	return att_map


def get_conditions(filters):

	if not (filters.get("fromdate") and filters.get("todate")):
		msgprint(_("Please select fromdate  and todate"), raise_exception=1)
	date1 = datetime.datetime.strptime(filters.get("fromdate"),"%Y-%m-%d").date()
	date2 = datetime.datetime.strptime(filters.get("todate"), "%Y-%m-%d").date()
	delta = date2 - date1
	for i in range(delta.days + 1):
		day = date1 + timedelta(days=i)
		filters["total_days_in_month"].append(day.strftime("%Y-%m-%d"))
	
	# for i in daterange(date1,date2):
	# 	print(i.strftime("%d"))
    # 	filters["total_days_in_month"].append(i.strftime("%d"))

	conditions = " and attendance_date  >=  %(fromdate)s and attendance_date <= %(todate)s"
	if filters.get("company"): conditions += " and company = %(company)s"
	if filters.get("employee"): conditions += " and employee = %(employee)s"

	return conditions, filters
def daterange(start_date, end_date):
    for n in range(int ((end_date - start_date).days)):
        yield start_date + timedelta(n)

def get_employee_details():
	emp_map = frappe._dict()
	for d in frappe.db.sql("""select name, employee_name, designation, department, branch, company,
		holiday_list from tabEmployee""", as_dict=1):
		emp_map.setdefault(d.name, d)

	return emp_map

def get_holiday(holiday_list, fromdate,todate):
	holiday_map = frappe._dict()
	for d in holiday_list:
		if d:
			holiday_map.setdefault(d, frappe.db.sql_list('''select holiday_date from `tabHoliday`
				where parent=%s and holiday_date>= %s and holiday_date <=  %s''', (d, fromdate,todate)))

	return holiday_map

@frappe.whitelist()
def get_attendance_years():
	year_list = frappe.db.sql_list("""select distinct YEAR(attendance_date) from tabAttendance ORDER BY YEAR(attendance_date) DESC""")
	if not year_list:
		year_list = [getdate().year]

	return "\n".join(str(year) for year in year_list)
