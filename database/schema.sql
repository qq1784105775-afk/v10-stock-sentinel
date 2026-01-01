CREATE TABLE IF NOT EXISTS stocks (
    ts_code TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    industry TEXT,
    list_date TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    pre_close REAL,
    change_pct REAL,
    vol REAL,
    amount REAL,
    UNIQUE(ts_code, trade_date)
);

CREATE TABLE IF NOT EXISTS money_flow (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    buy_sm_amount REAL,
    buy_md_amount REAL,
    buy_lg_amount REAL,
    buy_elg_amount REAL,
    sell_sm_amount REAL,
    sell_md_amount REAL,
    sell_lg_amount REAL,
    sell_elg_amount REAL,
    net_mf_amount REAL,
    main_net_inflow REAL,
    UNIQUE(ts_code, trade_date)
);

CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    add_price REAL,
    add_date TEXT NOT NULL,
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS data_cache (
    cache_key TEXT PRIMARY KEY,
    cache_data TEXT NOT NULL,
    expire_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS backtest_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_code TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    total_signals INTEGER,
    win_count INTEGER,
    lose_count INTEGER,
    win_rate REAL,
    avg_return REAL,
    max_return REAL,
    max_loss REAL,
    run_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS positions (
    ts_code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    total_qty INTEGER DEFAULT 0,
    available_qty INTEGER DEFAULT 0,
    cost_price REAL DEFAULT 0,
    market_value REAL DEFAULT 0,
    float_pnl REAL DEFAULT 0,
    realized_pnl REAL DEFAULT 0,
    last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_code TEXT NOT NULL,
    name TEXT NOT NULL,
    direction TEXT NOT NULL,
    qty INTEGER NOT NULL,
    price REAL NOT NULL,
    fee REAL DEFAULT 0,
    pnl REAL DEFAULT 0,
    trade_date TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_data(trade_date);
CREATE INDEX IF NOT EXISTS idx_daily_code ON daily_data(ts_code);
CREATE INDEX IF NOT EXISTS idx_flow_date ON money_flow(trade_date);
CREATE INDEX IF NOT EXISTS idx_flow_code ON money_flow(ts_code);
CREATE INDEX IF NOT EXISTS idx_cache_expire ON data_cache(expire_at);
CREATE INDEX IF NOT EXISTS idx_trades_code ON trades(ts_code);
CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(trade_date);

-- V10新增：推荐记录表（用于追踪准确率）
CREATE TABLE IF NOT EXISTS recommendation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_code TEXT NOT NULL,
    name TEXT NOT NULL,
    recommend_date TEXT NOT NULL,
    recommend_price REAL NOT NULL,
    recommend_score REAL NOT NULL,
    recommend_type TEXT NOT NULL,          -- 推荐类型：main_wave/rebound/golden/wash等
    recommend_reason TEXT,                  -- 推荐理由
    verify_date TEXT,                       -- 验证日期
    verify_price REAL,                      -- 验证时价格
    profit_pct REAL,                        -- 盈亏百分比
    result TEXT DEFAULT 'pending',          -- pending/win/lose
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- V10新增：龙虎榜记录表
CREATE TABLE IF NOT EXISTS dragon_tiger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    reason TEXT,                            -- 上榜原因
    buy_amount REAL,                        -- 买入总额
    sell_amount REAL,                       -- 卖出总额
    net_amount REAL,                        -- 净买入
    top_buyers TEXT,                        -- 买入前5营业部JSON
    top_sellers TEXT,                       -- 卖出前5营业部JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ts_code, trade_date)
);

-- V10新增：融资融券数据表
CREATE TABLE IF NOT EXISTS margin_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    rzye REAL,                              -- 融资余额
    rzmre REAL,                             -- 融资买入额
    rzche REAL,                             -- 融资偿还额
    rqye REAL,                              -- 融券余额
    rqmcl REAL,                             -- 融券卖出量
    rzrqye REAL,                            -- 融资融券余额
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ts_code, trade_date)
);

-- V10新增：板块联动数据表
CREATE TABLE IF NOT EXISTS sector_linkage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    sector_name TEXT NOT NULL,
    sector_pct REAL,                        -- 板块涨幅
    leader_code TEXT,                       -- 龙头股代码
    leader_name TEXT,                       -- 龙头股名称
    leader_pct REAL,                        -- 龙头涨幅
    follower_count INTEGER,                 -- 跟涨股数量
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(trade_date, sector_name)
);

CREATE INDEX IF NOT EXISTS idx_recommend_date ON recommendation_history(recommend_date);
CREATE INDEX IF NOT EXISTS idx_recommend_code ON recommendation_history(ts_code);
CREATE INDEX IF NOT EXISTS idx_recommend_result ON recommendation_history(result);
CREATE INDEX IF NOT EXISTS idx_dragon_date ON dragon_tiger(trade_date);
CREATE INDEX IF NOT EXISTS idx_margin_date ON margin_data(trade_date);
CREATE INDEX IF NOT EXISTS idx_sector_date ON sector_linkage(trade_date);
