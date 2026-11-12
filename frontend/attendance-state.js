export function shiftState(shift, time) {
  const start = Date.parse(shift.starts);
  const end = Date.parse(shift.ends);
  const missedIn = !shift.check_in && time >= end;
  const missedOut = Boolean(shift.check_in && !shift.check_out && time > end);
  const late = Boolean(shift.check_in && Date.parse(shift.check_in) > start && !shift.excused);
  return {
    canCheckIn: !shift.closed && !shift.check_in && start <= time && time < end,
    canCheckOut: !shift.closed && Boolean(shift.check_in) && !shift.check_out &&
      Date.parse(shift.check_in) < time && start <= time && time <= end,
    missedIn, missedOut, late,
    status: missedIn ? (shift.excused ? "excused_absence" : "absent") :
      !shift.check_in ? "not_checked_in" :
      shift.check_out ? "completed" : missedOut ? "missing_checkout" : "working"
  };
}

export function currentShift(shifts, time) {
  const sorted = [...shifts].sort((a,b) => Date.parse(a.starts)-Date.parse(b.starts));
  return sorted.find(s=>shiftState(s,time).canCheckOut) ||
    sorted.find(s=>shiftState(s,time).canCheckIn) || null;
}

export function weekBounds(time) {
  const local = new Date(time + 7*3600000);
  local.setUTCHours(0,0,0,0);
  const day = local.getUTCDay() || 7;
  local.setUTCDate(local.getUTCDate() - day + 1);
  const start = local.getTime() - 7*3600000;
  return {start, end:start+7*86400000};
}
