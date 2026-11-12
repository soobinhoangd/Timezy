CREATE TABLE IF NOT EXISTS shops (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE
);
INSERT OR IGNORE INTO shops VALUES (1, 'Đảo Matcha'), (2, 'Mixue');

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
    password TEXT NOT NULL, shop_id INTEGER REFERENCES shops(id),
    hourly_rate INTEGER NOT NULL DEFAULT 0 CHECK (hourly_rate >= 0)
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
    expires TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shifts (
    id INTEGER PRIMARY KEY, shop_id INTEGER NOT NULL REFERENCES shops(id),
    starts TEXT NOT NULL, ends TEXT NOT NULL CHECK (ends > starts),
    published INTEGER NOT NULL DEFAULT 0, UNIQUE (shop_id, starts, ends)
);
CREATE TABLE IF NOT EXISTS registrations (
    shift_id INTEGER NOT NULL REFERENCES shifts(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    PRIMARY KEY (shift_id, user_id)
);
CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY, shift_id INTEGER NOT NULL REFERENCES shifts(id),
    user_id INTEGER NOT NULL REFERENCES users(id), hourly_rate INTEGER NOT NULL,
    check_in TEXT, check_out TEXT, excused INTEGER NOT NULL DEFAULT 0,
    UNIQUE (shift_id, user_id)
);
CREATE TABLE IF NOT EXISTS periods (
    month TEXT PRIMARY KEY, opened TEXT NOT NULL, closed TEXT
);
CREATE TABLE IF NOT EXISTS statements (
    month TEXT NOT NULL REFERENCES periods(month), user_id INTEGER NOT NULL REFERENCES users(id),
    confirmed TEXT, PRIMARY KEY (month, user_id)
);
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY, attendance_id INTEGER NOT NULL REFERENCES attendance(id),
    kind TEXT NOT NULL CHECK (kind IN ('explanation','correction')),
    reason TEXT NOT NULL, proposed_in TEXT, proposed_out TEXT, previous_in TEXT, previous_out TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
    decision_reason TEXT, created TEXT NOT NULL, reviewed TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS one_pending_request
    ON requests(attendance_id) WHERE status = 'pending';
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
    message TEXT NOT NULL, created TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS shifts_by_shop_time ON shifts(shop_id, starts);
CREATE INDEX IF NOT EXISTS attendance_by_employee ON attendance(user_id, shift_id);
CREATE INDEX IF NOT EXISTS notifications_by_user ON notifications(user_id, id);
CREATE INDEX IF NOT EXISTS sessions_by_expiry ON sessions(expires);
CREATE TABLE IF NOT EXISTS account_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    role TEXT NOT NULL CHECK (role IN ('owner', 'employee')),
    status TEXT NOT NULL CHECK (status IN ('pending', 'active')),
    recovery_hash TEXT
);
CREATE TRIGGER IF NOT EXISTS employee_requires_approval
AFTER INSERT ON users
WHEN NEW.shop_id IS NOT NULL
BEGIN
    INSERT INTO account_profiles(user_id,role,status)
    VALUES (NEW.id,'employee','pending');
END;
CREATE TABLE IF NOT EXISTS account_details (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    birth_date TEXT NOT NULL,
    gender TEXT NOT NULL CHECK (gender IN ('male','female','other')),
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    phone TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS shift_templates (
    shop_id INTEGER NOT NULL REFERENCES shops(id),
    slot TEXT NOT NULL CHECK (slot IN ('morning','afternoon','evening','split')),
    starts TEXT,
    ends TEXT,
    PRIMARY KEY (shop_id,slot)
);
INSERT OR IGNORE INTO shift_templates(shop_id,slot,starts)
SELECT id,'morning',NULL FROM shops;
INSERT OR IGNORE INTO shift_templates(shop_id,slot,starts)
SELECT id,'afternoon',NULL FROM shops;
INSERT OR IGNORE INTO shift_templates(shop_id,slot,starts)
SELECT id,'evening','18:00' FROM shops;
INSERT OR IGNORE INTO shift_templates(shop_id,slot,starts)
SELECT id,'split','20:00' FROM shops;
UPDATE shift_templates SET starts=COALESCE(starts,'07:30'),ends=COALESCE(ends,'12:00')
WHERE slot='morning';
UPDATE shift_templates SET starts=COALESCE(starts,'12:00'),ends=COALESCE(ends,'18:00')
WHERE slot='afternoon';
UPDATE shift_templates SET starts=COALESCE(starts,'18:00'),ends=COALESCE(ends,'23:30')
WHERE slot='evening';
UPDATE shift_templates SET starts=COALESCE(starts,'20:00'),ends=COALESCE(ends,'23:30')
WHERE slot='split';
CREATE TABLE IF NOT EXISTS weekly_availability (
    user_id INTEGER NOT NULL REFERENCES users(id),
    day TEXT NOT NULL,
    slot TEXT NOT NULL CHECK (slot IN ('morning','afternoon','evening','split')),
    PRIMARY KEY (user_id,day,slot)
);
CREATE TABLE IF NOT EXISTS weekly_slots (
    shop_id INTEGER NOT NULL REFERENCES shops(id),
    day TEXT NOT NULL,
    slot TEXT NOT NULL,
    shift_id INTEGER NOT NULL UNIQUE REFERENCES shifts(id),
    PRIMARY KEY (shop_id,day,slot)
);
CREATE TABLE IF NOT EXISTS weekly_submissions (
    user_id INTEGER NOT NULL REFERENCES users(id),
    week_start TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    confirmed_at TEXT NOT NULL,
    PRIMARY KEY (user_id,week_start)
);
