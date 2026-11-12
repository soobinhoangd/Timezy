import {shiftState, currentShift, weekBounds} from "/attendance-state.js";

const root = document.getElementById("app");
const dialog = document.getElementById("dialog");
const feedback = document.getElementById("feedback");
let token = localStorage.getItem("timezy-token") || sessionStorage.getItem("timezy-token") || "";
let me = null;
let view = "home";
let shops = [];
let records = [];
let shifts = [];
let requests = [];
let periods = [];
let employees = [];
let registrations = [];
let weeklyMode = "current";
let weeklyData = null;
let weeklyDraft = new Set();
let weeklyEditing = false;
let weeklyDirty = false;
let selectedMonth = "";
let period = null;
let selectedShop = "";
let selectedDay = new Intl.DateTimeFormat("en-CA", {timeZone: "Asia/Ho_Chi_Minh"}).format(new Date());
let flashTimer;
let serverEpoch = Date.now();
let clockAnchor = performance.now();
let homeUpdating = false;
let clockOnline = true;
const currentTime = () => serverEpoch + performance.now() - clockAnchor;

async function syncClock() {
  const started = performance.now();
  const clock = await api("/clock");
  serverEpoch = Date.parse(clock.now) + (performance.now()-started)/2;
  clockAnchor = performance.now();
}
const statusLabels = {not_checked_in: "Chưa vào ca", working: "Đang làm", missing_checkout: "Thiếu giờ ra",
  completed: "Đã tan ca", absent: "Bỏ ca", excused_absence: "Vắng có lý do",
  pending: "Chờ duyệt", approved: "Đã duyệt", rejected: "Đã từ chối"};
const escape = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
const money = value => new Intl.NumberFormat("vi-VN", {style:"currency", currency:"VND"}).format(value);
const dateTime = value => value ? new Intl.DateTimeFormat("vi-VN", {timeZone:"Asia/Ho_Chi_Minh", day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit"}).format(new Date(value)) : "—";
const shopName = id => shops.find(item => item.id === id)?.name || "";
const owner = () => me?.role === "owner";
const button = (action, text, id = "", type = "") => '<button type="button" class="'+type+'" data-action="'+action+'" data-id="'+escape(id)+'">'+text+'</button>';
const empty = text => '<div class="empty">'+text+'</div>';
const iso = value => value + ":00+07:00";
const field = (name, label, type = "text", value = "", extra = "") => '<label>'+label+'<input name="'+name+'" type="'+type+'" value="'+escape(value)+'" required '+extra+'></label>';
const errorSlot = '<p class="error" role="alert"></p>';
const saveButton = '<button class="primary" type="submit">Lưu và gửi</button>';
const shopSelect = (name = "shop_id", all = false) => '<label>Cơ sở<select name="'+name+'">'+(all?'<option value="">Tất cả cơ sở</option>':"")+shops.map(s=>'<option value="'+s.id+'">'+escape(s.name)+'</option>').join("")+'</select></label>';
function flash(text) {
  clearTimeout(flashTimer);
  feedback.textContent = text;
  flashTimer = setTimeout(() => feedback.textContent = "", 5000);
}
async function api(path, data, binary = false) {
  const response = await fetch(path, {
    method: data === undefined ? "GET" : "POST",
    headers: {"Authorization": "Bearer "+token, "Content-Type":"application/json"},
    body: data === undefined ? undefined : JSON.stringify(data)
  });
  if (!response.ok) {
    const problem = await response.json().catch(() => ({error:"Không thể kết nối máy chủ."}));
    if (response.status === 401 && path !== "/login") {
      clearSession();
      renderLogin();
    }
    throw new Error(problem.error || "Yêu cầu chưa thành công.");
  }
  return binary ? response.blob() : response.json();
}
function clearSession() {
  localStorage.removeItem("timezy-token");
  sessionStorage.removeItem("timezy-token");
  token = "";
  me = null;
}
function showRecovery(code, message) {
  renderLogin();
  const form = root.querySelector("#login");
  form.innerHTML = '<h1>Lưu mã khôi phục</h1><p>'+escape(message)+'</p><p class="note">Cất mã này ở nơi riêng tư. Bạn sẽ cần mã để đặt lại mật khẩu khi quên.</p><textarea readonly aria-label="Mã khôi phục">'+escape(code)+'</textarea>'+button("auth-login","Đã lưu mã · Đăng nhập","","primary");
}
function renderLogin(mode = "login") {
  const signup = mode === "signup", reset = mode === "reset";
  const title = signup ? "Tạo tài khoản Timezy" : reset ? "Đặt lại mật khẩu" : "Đăng nhập Timezy";
  let fields = field("username",signup?"Tên tài khoản":"Tên đăng nhập","text","","autocomplete='username' maxlength='100'");
  if (signup) {
    const today = new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Ho_Chi_Minh"}).format(new Date());
    fields += field("birth_date","Ngày tháng năm sinh","date","","max='"+today+"' autocomplete='bday'")+
      '<label>Giới tính<select name="gender" required><option value="">Chọn giới tính</option><option value="male">Nam</option><option value="female">Nữ</option><option value="other">Khác</option></select></label>'+
      field("email","Email","email","","autocomplete='email' maxlength='254'")+
      field("phone","Số điện thoại","tel","","autocomplete='tel' maxlength='30'")+
      '<label>Loại tài khoản<select name="role"><option value="employee">Nhân viên</option><option value="owner">Chủ quán / Quản lý</option></select></label>'+
      '<label id="signup-shop">Cơ sở làm việc<select name="shop_id"><option value="1">Dao Matcha</option><option value="2">Mixue</option></select></label>';
  }
  if (reset) fields += field("recovery_code","Mã khôi phục","text","","autocomplete='off'");
  fields += field(reset?"new_password":"password",reset?"Mật khẩu mới":"Mật khẩu","password","",
    (signup||reset?"minlength='8' autocomplete='new-password'":"autocomplete='current-password'")+" maxlength='256'");
  if (signup || reset) fields += field("confirm_password","Nhập lại mật khẩu","password","","minlength='8' maxlength='256' autocomplete='new-password'");
  if (!signup && !reset) fields += '<label class="check"><input type="checkbox" name="remember" checked>Ghi nhớ đăng nhập trong 30 ngày</label>';
  root.innerHTML = '<div class="login"><section class="login-story"><div class="brand">timezy<span>·</span></div><h1>Mỗi ca làm.<br>Một ngày trọn vẹn.</h1><p translate="no">Dao Matcha &amp; Mixue</p><p>Lịch làm rõ ràng, chấm công thuận tiện và bảng công luôn trong tầm tay.</p></section><section class="login-form"><form id="login"><div><span class="eyebrow">Tài khoản của bạn</span><h1>'+title+'</h1><p class="muted">'+(signup?"Chọn vai trò của bạn. Tài khoản mới sẽ được chủ quán xét duyệt.":reset?"Nhập mã khôi phục đã lưu khi tạo tài khoản.":"Đăng nhập để quản lý ca làm và bảng công.")+'</p></div>'+fields+errorSlot+'<button type="submit" class="primary">'+(signup?"Đăng ký":reset?"Đặt lại mật khẩu":"Đăng nhập")+'</button><div class="row">'+(signup||reset?button("auth-login","Quay lại đăng nhập"):button("auth-signup","Tạo tài khoản")+button("auth-reset","Quên mật khẩu"))+'</div></form></section></div>';
  const form = root.querySelector("#login");
  if (signup) form.elements.role.addEventListener("change",()=>{
    form.querySelector("#signup-shop").hidden=form.elements.role.value==="owner";
  });
  form.addEventListener("submit", async event => {
    event.preventDefault();
    await submit(form, async values => {
      if (signup || reset) {
        if ((values.password || values.new_password) !== values.confirm_password) throw new Error("Hai mật khẩu chưa khớp.");
        const result = await api(signup?"/signup":"/reset-password", signup?
          {username:values.username,birth_date:values.birth_date,gender:values.gender,email:values.email,phone:values.phone,
            password:values.password,confirm_password:values.confirm_password,role:values.role,shop_id:Number(values.shop_id)}:
          {username:values.username,recovery_code:values.recovery_code,new_password:values.new_password});
        if (signup) {
          renderLogin();
          const login = root.querySelector("#login");
          login.elements.username.value = values.username;
          login.insertAdjacentHTML("beforeend", '<details><summary>Lưu mã khôi phục tài khoản</summary><p>Cất mã ở nơi riêng tư để dùng khi quên mật khẩu.</p><textarea readonly aria-label="Mã khôi phục">'+escape(result.recovery_code)+'</textarea></details>');
          flash(result.status==="pending"?"Đăng ký thành công. Vui lòng chờ chủ quán duyệt tài khoản.":"Đăng ký thành công. Bạn có thể đăng nhập.");
        } else {
          showRecovery(result.recovery_code, "Đã đặt lại mật khẩu và kết thúc các phiên đăng nhập cũ. Đây là mã khôi phục mới thay thế mã cũ.");
        }
        return;
      }
      const remember = values.remember === "on";
      const result = await api("/login", {username:values.username,password:values.password,remember});
      clearSession();
      token = result.token;
      (remember?localStorage:sessionStorage).setItem("timezy-token",token);
      view="home";
      await start();
    });
  });
}

async function start() {
  me = await api("/me");
  await syncClock();
  shops = await api("/shops");
  await refresh();
}
async function refresh() {
  [records, shifts, requests, periods] = await Promise.all([
    api("/attendance"), api("/shifts"), api("/requests"), api("/periods")
  ]);
  if (owner()) [employees, registrations] = await Promise.all([api("/employees"),api("/account-registrations")]);
  selectedMonth = periods.some(p=>p.month===selectedMonth) ? selectedMonth : periods[0]?.month || "";
  period = selectedMonth ? await api("/periods/"+selectedMonth) : null;
  if (view === "shifts") await loadWeekly();
  render();
}
function render() {
  const tabs = [["home", owner()?"Tổng quan":"Ca làm của tôi"],["shifts","Đăng ký & xếp ca"],["requests","Giải trình & bổ sung"],["payroll","Bảng công & lương"],["notifications","Thông báo"],["account","Tài khoản"]];
  if (owner()) tabs.push(["employees","Nhân viên"]);
  root.innerHTML = '<div class="shell"><aside><div><div class="brand">timezy<span>·</span></div><p translate="no">Dao Matcha &amp; Mixue</p></div><nav aria-label="Chức năng">'+tabs.map(([id,label])=>'<button data-action="navigate" data-id="'+id+'" class="'+(view===id?"active":"")+'" '+(view===id?'aria-current="page"':"")+'>'+label+'</button>').join("")+'</nav><div class="account"><div><strong>'+escape(me.name)+'</strong><p>'+ (owner()?"Chủ quán":escape(shopName(me.shop_id)))+'</p></div>'+button("logout","Đăng xuất")+'</div></aside><main><div class="topbar"><span class="muted">'+new Intl.DateTimeFormat("vi-VN",{dateStyle:"full",timeZone:"Asia/Ho_Chi_Minh"}).format(new Date())+'</span><span class="pill">'+(owner()?"Quản lý hai cơ sở":escape(shopName(me.shop_id)))+'</span></div><div id="content"></div></main></div>';
  const content = document.getElementById("content");
  if (view === "home") renderHome(content);
  if (view === "shifts") renderShifts(content);
  if (view === "requests") renderRequests(content);
  if (view === "payroll") renderPayroll(content);
  if (view === "employees") renderEmployees(content);
  if (view === "account") renderAccount(content);
  if (view === "notifications") {
    content.innerHTML = '<h1>Thông báo</h1><p class="muted">Lịch ca, kết quả xử lý và yêu cầu xác nhận.</p>';
    api("/notifications").then(items => {
      if (view === "notifications") content.innerHTML += items.length ? '<div class="grid">'+items.map(n=>'<article class="card"><span class="muted">'+dateTime(n.created)+'</span><p>'+escape(n.message)+'</p></article>').join("")+'</div>' : empty("Bạn chưa có thông báo.");
    }).catch(error=>flash(error.message));
  }
}
function attendanceCard(item) {
  let actions = "";

  if (!owner()) {
    const state = shiftState(item,currentTime());
    const pending = requests.some(r=>r.attendance_id===item.id && r.status==="pending");
    if (!item.closed && (state.late || state.missedIn || state.missedOut)) {
      actions += pending ? '<span class="pill">Giải trình đang chờ duyệt</span>' :
        button(state.missedIn || state.missedOut ? "explain-missing" : "explain","Giải trình",item.id);
    }
  }
  const live = owner() ? item : {...item,...shiftState(item,currentTime())};
  return '<article class="card"><span class="pill">'+escape(shopName(item.shop_id))+'</span><h3>'+dateTime(item.starts)+' → '+dateTime(item.ends)+'</h3>'+(owner()?'<p>'+escape(item.name)+'</p>':"")+'<p class="muted">'+statusLabels[live.status]+(live.late?" · Đi muộn":"")+'</p><p>Vào '+dateTime(item.check_in)+'<br>Ra '+dateTime(item.check_out)+'</p><div class="actions">'+actions+'</div></article>';
}
function renderEmployeeHome(content) {
  content.innerHTML = '<span class="eyebrow">Ca làm của tôi</span><h1>Chấm công hôm nay</h1>'+
    '<section class="hero checkin-hero"><div><span class="muted">Giờ Việt Nam</span><div id="live-clock" class="live-clock"></div></div>'+
    '<div id="current-attendance" aria-live="polite"></div></section>'+
    '<div class="row between"><div><h2>Lịch làm trong tuần</h2><p id="week-label" class="muted"></p></div>'+button("refresh","Cập nhật")+'</div>'+
    '<div id="weekly-shifts" class="grid"></div>'+button("schedule-issue","Báo quản lý chưa có ca");
  updateEmployeeHome();
}
function updateEmployeeHome() {
  if (!me || owner() || view!=="home") return;
  const clock = document.getElementById("live-clock");
  if (!clock) return;
  const time = currentTime();
  clock.textContent = new Intl.DateTimeFormat("vi-VN",{timeZone:"Asia/Ho_Chi_Minh",hour:"2-digit",minute:"2-digit",second:"2-digit",day:"2-digit",month:"2-digit",year:"numeric"}).format(time);
  const selected = currentShift(records,time);
  const next = [...records].filter(r=>Date.parse(r.starts)>time && !r.check_out).sort((a,b)=>Date.parse(a.starts)-Date.parse(b.starts))[0];
  const state = selected ? shiftState(selected,time) : null;
  const label = selected ? (state.canCheckOut?"Check-out · Tan ca":"Check-in · Vào ca") : "Check-in · Vào ca";
  const actionName = state?.canCheckOut ? "check-out" : "check-in";
  const html = '<h2>'+(selected?escape(shopName(selected.shop_id)):next?"Ca tiếp theo":"Chưa có ca trong giờ làm")+'</h2>'+
    '<p>'+(selected?dateTime(selected.starts)+' → '+dateTime(selected.ends):next?dateTime(next.starts)+' → '+dateTime(next.ends):"Bạn có thể xem lịch tuần và đăng ký thêm ca làm.")+'</p>'+
    '<button class="primary clock-action" type="button" data-action="'+actionName+'" data-id="'+(selected?.id||"")+'" '+(!selected||!clockOnline?'disabled':"")+'>'+label+'</button>'+
    '<p class="muted">'+(!clockOnline?"Mất kết nối. Đang đồng bộ lại giờ và dữ liệu.":selected?"Chấm công sẽ ghi nhận giờ thực tế trên máy chủ.":next?"Nút sẽ mở khi đến giờ bắt đầu ca.":"Nút chấm công mở khi có ca được xếp đang diễn ra.")+'</p>';
  const controls = document.getElementById("current-attendance");
  if (controls.dataset.markup!==html) { controls.innerHTML=html; controls.dataset.markup=html; }
  const week = weekBounds(time);
  const dayLabel = new Intl.DateTimeFormat("vi-VN",{timeZone:"Asia/Ho_Chi_Minh",day:"2-digit",month:"2-digit",year:"numeric"});
  document.getElementById("week-label").textContent="Thứ Hai – Chủ nhật · "+dayLabel.format(week.start)+" đến "+dayLabel.format(week.end-1);
  const weekly=records.filter(r=>Date.parse(r.starts)<week.end && Date.parse(r.ends)>week.start)
    .sort((a,b)=>Date.parse(a.starts)-Date.parse(b.starts));
  const list=document.getElementById("weekly-shifts");
  const cards=weekly.length?weekly.map(attendanceCard).join(""):empty("Bạn chưa được xếp ca trong tuần này.");
  if (list.dataset.markup!==cards) {list.innerHTML=cards; list.dataset.markup=cards;}
}
async function updateHomeData() {
  if (!me || owner() || view!=="home" || document.hidden || homeUpdating || dialog.open) return;
  homeUpdating=true;
  try {
    const [attendance, latestRequests] = await Promise.all([api("/attendance"),api("/requests"),syncClock()]);
    records=attendance;
    requests=latestRequests;
    clockOnline=true;
  } catch {
    clockOnline=false;
  } finally {
    homeUpdating=false;
    updateEmployeeHome();
  }
}
setInterval(updateEmployeeHome,1000);
setInterval(updateHomeData,15000);
document.addEventListener("visibilitychange",()=>{if(!document.hidden) updateHomeData();});
window.addEventListener("focus",updateHomeData);
window.addEventListener("online",updateHomeData);
window.addEventListener("offline",()=>{clockOnline=false; updateEmployeeHome();});


function renderHome(content) {
  if (!owner()) {renderEmployeeHome(content); return;}
  const today = records.filter(r => r.starts.slice(0,10)<=selectedDay && r.ends.slice(0,10)>=selectedDay && (!selectedShop || String(r.shop_id)===selectedShop));
  content.innerHTML = '<span class="eyebrow">Nhịp làm việc mỗi ngày</span><h1>'+ (owner()?"Hôm nay tại quán":"Ca làm của bạn")+'</h1><section class="hero"><h2>'+ (owner()?"Một nơi để theo dõi cả hai quán":"Sẵn sàng cho ca tiếp theo")+'</h2><p>'+ (owner()?"Theo dõi nhân viên vào ca, xử lý công và kiểm tra tiến độ xác nhận lương.":"Kiểm tra lịch được xếp, chấm giờ vào và giờ ra ngay tại ca của bạn.")+'</p>'+button("refresh","Cập nhật")+'</section><div class="filters"><label>Ngày xem<input type="date" id="day-filter" value="'+selectedDay+'"></label>'+(owner()?shopSelect("filter_shop",true):"")+'</div><div class="grid">'+today.map(attendanceCard).join("")+'</div>'+(!today.length?empty("Chưa có ca được xếp cho ngày này."):"")+(owner()?"":button("schedule-issue","Báo quản lý chưa có ca"));
  const day = content.querySelector("#day-filter");
  day.addEventListener("change",()=>{selectedDay=day.value; render();});
  const shop = content.querySelector("[name=filter_shop]");
  if (shop) {shop.value=selectedShop; shop.addEventListener("change",()=>{selectedShop=shop.value; render();});}
}
function renderShifts(content) {
  if (!weeklyData) {content.innerHTML=empty("Đang tải lịch tuần…"); return;}
  const dateLabel=new Intl.DateTimeFormat("vi-VN",{day:"2-digit",month:"2-digit",timeZone:"Asia/Ho_Chi_Minh"});
  const heading = '<div class="row between"><div><span class="eyebrow">Lịch làm việc</span><h1>Đăng ký & xếp ca</h1></div>'+(owner()?button("weekly-config","Cấu hình giờ ca"):"")+'</div>'+
    '<div class="week-tabs" role="tablist" aria-label="Lịch làm việc">'+
    '<button role="tab" aria-selected="'+(weeklyMode==="current")+'" data-action="weekly-tab" data-id="current">Lịch tuần này</button>'+
    '<button role="tab" aria-selected="'+(weeklyMode==="next")+'" data-action="weekly-tab" data-id="next">Đăng ký lịch tuần sau</button></div>'+
    '<div class="filters">'+(owner()?shopSelect("weekly-shop"):"")+'<span class="pill">'+escape(shopName(weeklyData.shop_id))+' · '+dateLabel.format(new Date(weeklyData.days[0]+"T00:00:00+07:00"))+' – '+dateLabel.format(new Date(weeklyData.days[6]+"T00:00:00+07:00"))+'</span></div>';
  const days=weeklyData.days;
  const headers=days.map((day,index)=>'<th scope="col">'+(index===6?"Chủ nhật":"Thứ "+(index+2))+'<br>'+dateLabel.format(new Date(day+"T00:00:00+07:00"))+'</th>').join("");
  const names={morning:"Ca sáng",afternoon:"Ca chiều",evening:"Tối full",split:"Tối gãy"};
  let table="";
  if (weeklyMode==="current") {
    table='<p class="muted">Lịch đã công bố của tất cả nhân viên trong quán.</p><div class="table-wrap"><table class="week-table"><thead><tr><th scope="col">Nhân viên</th>'+headers+'</tr></thead><tbody>'+
      weeklyData.employees.map(employee=>'<tr><th scope="row">'+escape(employee.name)+'</th>'+days.map(day=>{
        const start=Date.parse(day+"T00:00:00+07:00"),end=start+86400000;
        const assigned=weeklyData.schedule.filter(s=>s.user_id===employee.id && Date.parse(s.starts)<end && Date.parse(s.ends)>start);
        return '<td>'+assigned.map(s=>{
          const match=weeklyData.templates.find(t=>t.starts===s.starts.slice(11,16));
          const name=match?names[match.slot]:"Ca làm";
          return '<div class="schedule-chip">'+name+'<br><small>'+escape(s.starts.slice(11,16))+'–'+escape(s.ends.slice(11,16))+(s.starts.slice(0,10)!==s.ends.slice(0,10)?" · qua đêm":"")+'</small></div>';
        }).join("")+(!assigned.length?'<span class="muted">—</span>':"")+'</td>';
      }).join("")+'</tr>').join("")+'</tbody></table></div>'+
      (!weeklyData.employees.length?empty("Quán chưa có nhân viên đã được duyệt."):"");
  } else {
    table='<p class="muted">'+(owner()?"Chọn từng ô để xem nhân viên đăng ký và công bố ca.":"Tích các ca có thể đi làm, sau đó bấm Xác nhận đăng ký để gửi cho chủ quán.")+'</p>'+
      '<div class="table-wrap"><table class="week-table registration-table"><thead><tr><th scope="col">Ca làm</th>'+headers+'</tr></thead><tbody>'+
      Object.entries(names).map(([slot,name])=>{
        const template=weeklyData.templates.find(t=>t.slot===slot);
        const hours=template?.starts && template?.ends ? template.starts+"–"+template.ends:
          template?.starts ? "Từ "+template.starts+" · chưa đặt giờ kết thúc" : "Chưa cấu hình giờ";
        return '<tr><th scope="row">'+name+'<br><small class="muted">'+escape(hours)+'</small></th>'+
          days.map(day=>{
            const cell=weeklyData.cells.find(c=>c.day===day && c.slot===slot);
            if(owner()) return '<td>'+(cell.published?'<span class="pill">Đã công bố</span>':
              '<div class="candidate-list">'+cell.candidates.map(c=>'<span>'+escape(c.name)+'</span>').join("")+'</div>'+
              (cell.candidates.length?button("weekly-pick","Xếp ca",day+"|"+slot):'<span class="muted">Chưa ai đăng ký</span>'))+'</td>';
            const checked=weeklyDraft.has(day+"|"+slot);
            return '<td><label class="slot-check '+(checked?"is-checked":"")+'"><input type="checkbox" data-weekday="'+day+'" data-slot="'+slot+'" '+(checked?"checked ":"")+((cell.published||!weeklyEditing)?"disabled ":"")+' aria-label="'+escape(name+" ngày "+day)+'"><span>'+(cell.published?"Đã chốt":checked?"Đã chọn":"Có thể làm")+'</span></label></td>';
          }).join("")+'</tr>';
      }).join("")+'</tbody></table></div>'+
      (!owner()?'<div class="row between registration-actions"><div><p id="week-count">Đã chọn '+weeklyDraft.size+' ca</p><span class="pill">'+(weeklyEditing?"Đang chỉnh sửa · Chưa gửi": "Đã xác nhận đăng ký")+'</span></div><div class="actions">'+
        (weeklyEditing?button("weekly-confirm",weeklyData.submission?"Xác nhận thay đổi":"Xác nhận đăng ký","","primary")+button("weekly-cancel","Hủy chỉnh sửa"):
          button("weekly-edit","Chỉnh sửa đăng ký","","primary"))+'</div></div>':"");
  }
  content.innerHTML=heading+table;
  const shop=content.querySelector("[name=weekly-shop]");
  if(shop) {shop.value=String(weeklyData.shop_id);shop.addEventListener("change",async()=>{
    selectedShop=shop.value;
    try{await loadWeekly();render();}catch(error){flash(error.message);}
  });}
}
async function loadWeekly() {
  const branch=owner()?(selectedShop||String(shops[0]?.id)):String(me.shop_id);
  weeklyData=await api("/weekly?week="+weeklyMode+"&shop_id="+encodeURIComponent(branch));
  weeklyDraft=new Set(weeklyData.cells.filter(c=>c.registered).map(c=>c.day+"|"+c.slot));
  weeklyEditing=!weeklyData.submission;
  weeklyDirty=false;
}
root.addEventListener("change",async event=>{
  const input=event.target;
  if(!input.matches("input[data-weekday]")) return;
  const key=input.dataset.weekday+"|"+input.dataset.slot;
  if(input.checked) weeklyDraft.add(key);
  else weeklyDraft.delete(key);
  weeklyDirty=weeklyData.cells.some(cell=>cell.registered!==weeklyDraft.has(cell.day+"|"+cell.slot));
  input.closest("label").classList.toggle("is-checked",input.checked);
  input.nextElementSibling.textContent=input.checked?"Đã chọn":"Có thể làm";
  document.getElementById("week-count").textContent="Đã chọn "+weeklyDraft.size+" ca";
});

function discardWeeklyDraft() {
  if(weeklyDirty && !window.confirm("Đăng ký chưa được xác nhận. Bạn muốn bỏ các thay đổi?")) return false;
  weeklyDirty=false;
  return true;
}
window.addEventListener("beforeunload",event=>{
  if(weeklyDirty) {event.preventDefault();event.returnValue="";}
});


function renderRequests(content) {
  content.innerHTML = '<h1>Giải trình & bổ sung công</h1><p class="muted">'+(owner()?"Đối chiếu từng yêu cầu với lịch ca và giờ chấm thực tế.":"Gửi yêu cầu từ ca làm hoặc bảng công của bạn.")+'</p><div class="grid">'+requests.map(r=>'<article class="card"><span class="pill">'+statusLabels[r.status]+'</span><h3>'+escape(r.name)+' · '+(r.kind==="explanation"?"Giải trình":"Bổ sung công")+'</h3><p class="muted">'+escape(shopName(r.shop_id))+' · '+dateTime(r.starts)+' → '+dateTime(r.ends)+'</p><p>Đã ghi '+dateTime(r.check_in)+' → '+dateTime(r.check_out)+'</p>'+(r.proposed_in?'<p>Đề nghị '+dateTime(r.proposed_in)+' → '+dateTime(r.proposed_out)+'</p>':"")+'<p>'+escape(r.reason)+'</p>'+(r.decision_reason?'<p>Lý do từ chối · '+escape(r.decision_reason)+'</p>':"")+(owner() && r.status==="pending"?'<div class="actions">'+button("approve","Duyệt",r.id,"primary")+button("reject","Từ chối",r.id,"danger")+'</div>':"")+'</article>').join("")+'</div>'+(!requests.length?empty("Chưa có yêu cầu giải trình hoặc bổ sung công."):"");
}
function entriesTable(entries) {
  return '<div class="table-wrap"><table><thead><tr><th>Nhân viên</th><th>Ca</th><th>Giờ vào</th><th>Giờ ra</th><th>Giờ công</th><th>Tiền công</th><th>Thao tác</th></tr></thead><tbody>'+entries.map(e=>'<tr><td>'+escape(e.name)+'</td><td>'+dateTime(e.starts)+'</td><td>'+dateTime(e.check_in)+'</td><td>'+dateTime(e.check_out)+'</td><td>'+(e.seconds_worked/3600).toFixed(2)+'</td><td>'+money(e.pay)+'</td><td>'+(!owner()&&!period.closed?button("correct","Bổ sung",e.id):"")+'</td></tr>').join("")+'</tbody></table></div>';
}
function renderPayroll(content) {
  content.innerHTML = '<h1>Bảng công & lương</h1><p class="muted">Mùng 9 hằng tháng, xác nhận công và lương của tháng trước.</p>';
  if (!period) {content.innerHTML+=empty("Chưa có kỳ công đến hạn xác nhận."); return;}
  content.innerHTML += '<div class="filters"><label>Kỳ công<select id="period-select">'+periods.map(p=>'<option value="'+p.month+'" '+(p.month===selectedMonth?"selected":"")+'>'+p.month+'</option>').join("")+'</select></label><span class="pill">'+(period.closed?"Đã chốt kỳ":"Đang xác nhận")+'</span></div>';
  if (owner()) {
    content.innerHTML += '<div class="grid">'+period.shops.map(s=>'<article class="card"><h3>'+escape(s.name)+'</h3><div class="metric">'+s.confirmed+' / '+s.total+'</div><p class="muted">Nhân viên đã xác nhận</p></article>').join("")+'</div><h2>Tiến độ nhân viên</h2><div class="grid">'+period.employees.map(e=>'<div class="card"><h3>'+escape(e.name)+'</h3><p>'+escape(shopName(e.shop_id))+'</p><span class="pill">'+(e.confirmed?"Đã xác nhận":"Chờ xác nhận")+'</span></div>').join("")+'</div>';
    const ready = !period.pending_requests && period.employees.every(e=>e.confirmed);
    content.innerHTML += '<div class="actions">'+(period.closed?button("export","Tải bảng công Excel","","primary"):'<button class="primary" data-action="close" '+(!ready?"disabled":"")+'>Chốt kỳ công</button>')+'</div>'+(period.pending_requests?'<p class="note">Còn yêu cầu bổ sung hoặc giải trình đang chờ duyệt.</p>':"");
    content.innerHTML += '<h2 style="margin-top:28px">Bảng công đã xác nhận</h2>'+entriesTable(period.confirmed_statements.flatMap(s=>s.entries));
  } else {
    content.innerHTML += '<div class="grid"><article class="card"><span class="muted">Tổng giờ công</span><div class="metric">'+(period.total_seconds/3600).toFixed(2)+'</div></article><article class="card"><span class="muted">Lương tạm tính</span><div class="metric">'+money(period.total_pay)+'</div></article></div>'+entriesTable(period.entries)+'<div class="actions">'+(period.confirmed?'<span class="pill">Bạn đã xác nhận bảng công</span>':button("confirm","Xác nhận đủ công và lương","","primary"))+'</div>';
  }
  content.querySelector("#period-select").addEventListener("change",async event=>{
    selectedMonth=event.target.value;
    try {period=await api("/periods/"+selectedMonth); render();} catch(error){flash(error.message);}
  });
}
function renderEmployees(content) {
  content.innerHTML='<div class="row between"><h1>Nhân viên</h1>'+button("employee","Thêm nhân viên","","primary")+'</div><p class="muted">Mỗi người thuộc một cơ sở và có đơn giá theo giờ riêng.</p><div class="grid">'+employees.map(e=>'<article class="card"><span class="pill">'+escape(shopName(e.shop_id))+'</span><h3>'+escape(e.name)+'</h3><p class="muted">'+escape(e.username)+'</p><p>'+money(e.hourly_rate)+' / giờ</p></article>').join("")+'</div>'+(!employees.length?empty("Chưa có nhân viên. Hãy tạo tài khoản đầu tiên."):"");
  content.innerHTML += '<h2>Tài khoản chờ duyệt</h2><p class="muted">Mọi nhân viên mới đều cần chủ quán duyệt trước khi đăng nhập.</p><div class="grid">'+registrations.map(account=>'<article class="card"><h3>'+escape(account.name)+'</h3><p>'+escape(account.username)+'</p><p>'+(account.role==="owner"?"Chủ quán / Quản lý":escape(shopName(account.shop_id)))+'</p>'+button("approve-account","Duyệt tài khoản",account.id,"primary")+'</article>').join("")+'</div>'+(!registrations.length?empty("Không có tài khoản chờ duyệt."):"");
}

function renderAccount(content) {
  content.innerHTML='<h1>Tài khoản của bạn</h1><p class="muted">'+escape(me.name)+'</p><div class="grid"><section class="card"><h2>Đổi mật khẩu</h2><form id="change-password">'+field("current_password","Mật khẩu hiện tại","password","","autocomplete='current-password' maxlength='256'")+field("new_password","Mật khẩu mới","password","","minlength='8' maxlength='256' autocomplete='new-password'")+field("confirm_password","Nhập lại mật khẩu mới","password","","minlength='8' maxlength='256' autocomplete='new-password'")+errorSlot+'<button type="submit" class="primary">Đổi mật khẩu</button></form></section><section class="card"><h2>Mã khôi phục</h2><p>Tạo mã và lưu riêng để đặt lại mật khẩu nếu quên. Mã mới sẽ thay thế mã cũ.</p><form id="recovery-code">'+field("current_password","Xác nhận mật khẩu hiện tại","password","","autocomplete='current-password' maxlength='256'")+errorSlot+'<button type="submit">Tạo mã khôi phục mới</button></form><div id="recovery-result" aria-live="polite"></div></section></div>';
  content.querySelector("#change-password").addEventListener("submit", async event=>{
    event.preventDefault();
    await submit(event.target,async values=>{
      if(values.new_password!==values.confirm_password) throw new Error("Hai mật khẩu mới chưa khớp.");
      await api("/change-password",{current_password:values.current_password,new_password:values.new_password});
      clearSession();
      renderLogin();
      flash("Đã đổi mật khẩu. Vui lòng đăng nhập lại.");
    });
  });
  content.querySelector("#recovery-code").addEventListener("submit",async event=>{
    event.preventDefault();
    await submit(event.target,async values=>{
      const result=await api("/recovery-code",values);
      event.target.reset();
      content.querySelector("#recovery-result").innerHTML='<p class="note">Lưu mã ở nơi riêng tư.</p><textarea readonly aria-label="Mã khôi phục">'+escape(result.recovery_code)+'</textarea>';
    });
  });
}
function modal(title, body, onSave, label = "Lưu và gửi") {
  dialog.innerHTML='<form><div class="row between"><h2 id="dialog-title">'+title+'</h2>'+button("cancel","Đóng")+'</div>'+body+errorSlot+'<button type="submit" class="primary">'+label+'</button></form>';
  dialog.showModal();
  dialog.querySelector("form").addEventListener("submit", async event => {
    event.preventDefault();
    await submit(event.target, async (values, formData) => {
      await onSave(values,formData);
      dialog.close();
      flash("Đã cập nhật thành công.");
      await refresh();
    });
  });
}
async function submit(form, action) {
  const submitButton = form.querySelector("[type=submit], button:not([type])");
  const error = form.querySelector(".error");
  error.textContent="";
  submitButton.disabled=true;
  try {
    const formData=new FormData(form);
    await action(Object.fromEntries(formData),formData);
  } catch(problem) {error.textContent=problem.message;}
  finally {submitButton.disabled=false;}
}
async function action(name,id) {
  if (name==="weekly-tab") {if(!discardWeeklyDraft()) return;weeklyMode=id;await loadWeekly();render();return;}
  if (name==="weekly-edit") {weeklyEditing=true;render();return;}
  if (name==="weekly-cancel") {
    if(!discardWeeklyDraft()) return;
    weeklyDraft=new Set(weeklyData.cells.filter(c=>c.registered).map(c=>c.day+"|"+c.slot));
    weeklyEditing=!weeklyData.submission;
    render();return;
  }
  if (name==="weekly-confirm") {
    modal("Xác nhận đăng ký tuần sau",
      '<p>'+ (weeklyDraft.size?"Bạn chọn "+weeklyDraft.size+" ca trong tuần bắt đầu "+escape(weeklyData.days[0])+".":"Bạn xác nhận không đăng ký ca nào trong tuần này.")+'</p><p>Chủ quán sẽ nhận các lựa chọn sau khi bạn xác nhận.</p>',
      async ()=>{
        await api("/weekly/confirm",{week_start:weeklyData.days[0],revision:weeklyData.submission?.revision||0,
          slots:[...weeklyDraft].map(key=>{const [day,slot]=key.split("|");return {day,slot};})});
        weeklyDirty=false;
      },"Xác nhận đăng ký");
    return;
  }
  if (name==="weekly-config") {
    const labels={morning:"Ca sáng",afternoon:"Ca chiều",evening:"Tối full",split:"Tối gãy"};
    modal("Cấu hình giờ ca",
      '<p class="muted">'+escape(shopName(weeklyData.shop_id))+' · Giờ Việt Nam. Giờ kết thúc nhỏ hơn giờ bắt đầu được hiểu là qua đêm. Ca đã công bố giữ giờ đã xếp.</p>'+
      Object.entries(labels).map(([slot,label])=>{
        const template=weeklyData.templates.find(t=>t.slot===slot);
        return '<h3>'+label+'</h3><div class="time-pair">'+field(slot+"_starts","Bắt đầu","time",template?.starts||"",slot==="evening"||slot==="split"?"readonly":"")+
          field(slot+"_ends","Kết thúc","time",template?.ends||"")+'</div>';
      }).join(""),
      values=>api("/weekly/settings",{shop_id:weeklyData.shop_id,templates:Object.keys(labels).map(slot=>({slot,starts:values[slot+"_starts"],ends:values[slot+"_ends"]}))}),"Lưu giờ ca");
    return;
  }
  if (name==="weekly-pick") {
    const [day,slot]=id.split("|");
    const cell=weeklyData.cells.find(c=>c.day===day && c.slot===slot);
    modal("Chọn nhân viên cho ca "+day,cell.candidates.map(c=>'<label class="check"><input type="checkbox" name="employee_ids" value="'+c.id+'">'+escape(c.name)+'</label>').join(""),
      (_,data)=>api("/weekly/publish",{shop_id:weeklyData.shop_id,day,slot,employee_ids:data.getAll("employee_ids").map(Number)}),"Công bố ca");
    return;
  }
  if (name==="auth-login") {renderLogin(); return;}
  if (name==="auth-signup") {renderLogin("signup"); return;}
  if (name==="auth-reset") {renderLogin("reset"); return;}
  if (name==="approve-account") {
    const account=registrations.find(item=>String(item.id)===id);
    modal("Duyệt tài khoản "+escape(account?.name),
      account?.role==="employee"?field("hourly_rate","Đơn giá mỗi giờ bằng đồng","number",String(account.hourly_rate || 25000),"min='0' max='10000000' step='1'"):
      '<p>Tài khoản này sẽ có quyền quản lý cả hai cơ sở.</p>',
      values=>api("/account-registrations/"+id+"/approve",{hourly_rate:Number(values.hourly_rate||0)}),"Duyệt tài khoản");
    return;
  }
  if (name==="cancel") {dialog.close(); return;}
  if (name==="navigate") {if(!discardWeeklyDraft()) return;view=id; await refresh(); return;}
  if (name==="logout") {await api("/logout",{}); clearSession(); renderLogin(); return;}
  if (name==="refresh") {await refresh(); flash("Dữ liệu đã cập nhật."); return;}
  if (name==="register") {await api("/shifts/"+id+"/register",{}); await refresh(); flash("Đã đăng ký ca."); return;}
  if (name==="check-in" || name==="check-out") {await api("/attendance/"+id+"/"+name,{}); await refresh(); flash(name==="check-in"?"Đã ghi nhận giờ vào ca.":"Đã ghi nhận giờ tan ca."); return;}
  if (name==="schedule-issue") {modal("Báo quản lý chưa có ca",'<label>Nội dung<textarea name="reason" required maxlength="1000"></textarea></label>',v=>api("/schedule-issues",v)); return;}
  if (name==="create-shift" || name==="reschedule") {
    const existing=shifts.find(s=>String(s.id)===id);
    modal(name==="create-shift"?"Mở ca đăng ký":"Đổi giờ ca",
      (name==="create-shift"?shopSelect():'<p class="note">Nhân viên sẽ nhận thông báo và đăng ký lại theo giờ mới.</p>')+
      field("starts","Bắt đầu theo giờ Việt Nam","datetime-local",existing?.starts.slice(0,16) || "")+
      field("ends","Kết thúc theo giờ Việt Nam","datetime-local",existing?.ends.slice(0,16) || ""),
      v=>api(name==="create-shift"?"/shifts":"/shifts/"+id+"/reschedule",
        {...(v.shop_id?{shop_id:Number(v.shop_id)}:{}),starts:iso(v.starts),ends:iso(v.ends)}));
    return;
  }
  if (name==="candidates") {
    const candidates=await api("/shifts/"+id+"/candidates");
    if (!candidates.length) {flash("Chưa có nhân viên đăng ký ca này."); return;}
    modal("Chọn nhân viên đã đăng ký",candidates.map(c=>'<label class="check"><input type="checkbox" name="employee_ids" value="'+c.id+'">'+escape(c.name)+'</label>').join(""),
      (_,data)=>api("/shifts/"+id+"/publish",{employee_ids:data.getAll("employee_ids").map(Number)}),"Công bố lịch");
    return;
  }
  if (name==="explain" || name==="correct" || name==="explain-missing") {
    const correction = name!=="explain";
    const item=records.find(r=>String(r.id)===id);
    modal(correction?"Giải trình quên chấm công":"Giải trình đi muộn",
      '<p class="muted">Ca '+dateTime(item?.starts)+'</p>'+
      (correction?field("check_in","Ngày và giờ vào theo giờ Việt Nam","datetime-local",item?.check_in?.slice(0,16)||"")+field("check_out","Ngày và giờ ra theo giờ Việt Nam","datetime-local",item?.check_out?.slice(0,16)||""):"")+
      '<label>Lý do<textarea name="reason" required maxlength="1000"></textarea></label>',
      v=>api("/attendance/"+id+"/requests",{kind:correction?"correction":"explanation",reason:v.reason,
        ...(correction?{check_in:iso(v.check_in),check_out:iso(v.check_out)}:{})}));
    return;
  }
  if (name==="approve" || name==="reject") {
    modal(name==="approve"?"Duyệt yêu cầu":"Từ chối yêu cầu",
      name==="reject"?'<label>Lý do từ chối<textarea name="reason" required maxlength="1000"></textarea></label>':'<p>Xác nhận bạn đã đối chiếu lịch ca, giờ chấm công và nội dung yêu cầu.</p>',
      v=>api("/requests/"+id+"/review",{approve:name==="approve",...v}),name==="approve"?"Duyệt yêu cầu":"Gửi từ chối");
    return;
  }
  if (name==="employee") {
    modal("Thêm nhân viên",field("name","Họ tên")+field("username","Tên đăng nhập")+field("password","Mật khẩu","password","","minlength='8' maxlength='256' autocomplete='new-password'")+shopSelect()+field("hourly_rate","Đơn giá mỗi giờ bằng đồng","number","25000","min='0' max='10000000' step='1'"),
      v=>api("/employees",{...v,shop_id:Number(v.shop_id),hourly_rate:Number(v.hourly_rate)}));
    return;
  }
  if (name==="confirm" || name==="close") {
    modal(name==="confirm"?"Xác nhận bảng công":"Chốt kỳ công",'<p>'+ (name==="confirm"?"Xác nhận bạn đã kiểm tra đầy đủ các ca và tiền công của kỳ "+selectedMonth+".":"Chốt kỳ "+selectedMonth+" sau khi đủ nhân viên xác nhận. Các bản ghi công sẽ được khóa.")+'</p>',
      ()=>api("/periods/"+selectedMonth+"/"+name,{}),"Xác nhận");
    return;
  }
  if (name==="export") {
    const blob=await api("/periods/"+selectedMonth+"/export",undefined,true);
    const url=URL.createObjectURL(blob);
    const link=document.createElement("a");
    link.href=url; link.download="bang-cong-"+selectedMonth+".xlsx"; link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
}
async function clickHandler(event) {
  const target=event.target.closest("[data-action]");
  if (!target || target.disabled) return;
  target.disabled=true;
  try {await action(target.dataset.action,target.dataset.id);}
  catch(error){flash(error.message);}
  finally {target.disabled=false;}
}
root.addEventListener("click",clickHandler);
dialog.addEventListener("click",clickHandler);
if (token) start().catch(error=>{renderLogin(); flash(error.message);});
else renderLogin();
