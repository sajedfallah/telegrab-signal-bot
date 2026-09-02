from __future__ import annotations

import secrets
import sqlite3
import json
import hashlib
import math
import re
import string
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "nexus_bot.db"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def conn():
    con = sqlite3.connect(DB_PATH, timeout=10.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 10000")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}


def init_db() -> None:
    with conn() as con:
        # WAL greatly reduces reader/writer contention between handlers and workers.
        con.execute("PRAGMA journal_mode = WAL")
        con.execute("PRAGMA synchronous = NORMAL")
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                language TEXT,
                joined_public INTEGER NOT NULL DEFAULT 0,
                last_menu_message_id INTEGER,
                referral_code TEXT UNIQUE,
                referred_by INTEGER,
                points_balance INTEGER NOT NULL DEFAULT 0,
                referral_rewarded INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (referred_by) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                plan_code TEXT NOT NULL,
                days INTEGER NOT NULL,
                price_label TEXT NOT NULL,
                base_amount_irr INTEGER,
                final_amount_irr INTEGER,
                discount_percent REAL NOT NULL DEFAULT 0,
                promo_code TEXT,
                points_used INTEGER NOT NULL DEFAULT 0,
                payment_method TEXT NOT NULL DEFAULT 'irr',
                receipt_file_id TEXT NOT NULL,
                receipt_type TEXT NOT NULL,
                receipt_message_id INTEGER,
                status TEXT NOT NULL DEFAULT 'pending',
                admin_id INTEGER,
                admin_note TEXT,
                created_at TEXT NOT NULL,
                reviewed_at TEXT,
                FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS licenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                payment_id INTEGER,
                plan_code TEXT,
                source TEXT NOT NULL DEFAULT 'payment',
                vip_access INTEGER NOT NULL DEFAULT 1,
                autotrade_access INTEGER NOT NULL DEFAULT 1,
                granted_by INTEGER,
                starts_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                vip_expires_at TEXT,
                autotrade_expires_at TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                FOREIGN KEY (telegram_id) REFERENCES users(telegram_id),
                FOREIGN KEY (payment_id) REFERENCES payments(id)
            );

            CREATE TABLE IF NOT EXISTS invite_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                license_id INTEGER NOT NULL,
                invite_link TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                used_at TEXT,
                revoked_at TEXT,
                FOREIGN KEY (telegram_id) REFERENCES users(telegram_id),
                FOREIGN KEY (license_id) REFERENCES licenses(id)
            );

            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_id INTEGER NOT NULL,
                days_before INTEGER NOT NULL,
                sent_at TEXT NOT NULL,
                UNIQUE(license_id, days_before),
                FOREIGN KEY (license_id) REFERENCES licenses(id)
            );

            CREATE TABLE IF NOT EXISTS referral_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL UNIQUE,
                points INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'rewarded',
                created_at TEXT NOT NULL,
                FOREIGN KEY (referrer_id) REFERENCES users(telegram_id),
                FOREIGN KEY (referred_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS point_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                reason TEXT NOT NULL,
                ref_id TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS discounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                title_fa TEXT,
                title_en TEXT,
                percent REAL NOT NULL,
                max_uses INTEGER,
                used_count INTEGER NOT NULL DEFAULT 0,
                starts_at TEXT,
                expires_at TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_by INTEGER,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS discount_uses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discount_id INTEGER NOT NULL,
                telegram_id INTEGER NOT NULL,
                payment_id INTEGER,
                created_at TEXT NOT NULL,
                UNIQUE(discount_id, telegram_id),
                FOREIGN KEY (discount_id) REFERENCES discounts(id),
                FOREIGN KEY (telegram_id) REFERENCES users(telegram_id),
                FOREIGN KEY (payment_id) REFERENCES payments(id)
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admin_receipts (
                payment_id INTEGER NOT NULL,
                admin_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(payment_id, admin_id)
            );

            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title_fa TEXT NOT NULL,
                title_en TEXT NOT NULL,
                percent REAL NOT NULL,
                plan_code TEXT,
                audience TEXT NOT NULL DEFAULT 'all',
                starts_at TEXT,
                expires_at TEXT,
                max_uses INTEGER,
                used_count INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_by INTEGER,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS campaign_uses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                telegram_id INTEGER NOT NULL,
                payment_id INTEGER,
                created_at TEXT NOT NULL,
                UNIQUE(campaign_id, telegram_id),
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
                FOREIGN KEY (telegram_id) REFERENCES users(telegram_id),
                FOREIGN KEY (payment_id) REFERENCES payments(id)
            );

            CREATE TABLE IF NOT EXISTS broadcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                target TEXT NOT NULL,
                message_text TEXT NOT NULL,
                total_count INTEGER NOT NULL DEFAULT 0,
                sent_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'created',
                created_at TEXT NOT NULL,
                finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS auto_trade_waitlist (
                telegram_id INTEGER PRIMARY KEY,
                joined_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS trials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL UNIQUE,
                days INTEGER NOT NULL,
                granted_by INTEGER NOT NULL,
                granted_at TEXT NOT NULL,
                FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_id INTEGER,
                details TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                publish_token TEXT UNIQUE,
                market_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL DEFAULT 'M5',
                direction TEXT NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL NOT NULL,
                tp1 REAL NOT NULL,
                tp2 REAL,
                tp3 REAL,
                risk_percent REAL NOT NULL,
                rr_ratio REAL,
                destination TEXT NOT NULL,
                chart_file_id TEXT,
                free_message_id INTEGER,
                vip_message_id INTEGER,
                free_last_message_id INTEGER,
                vip_last_message_id INTEGER,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                partial_percent REAL,
                trailing_value TEXT,
                volume_mode TEXT NOT NULL DEFAULT 'RISK',
                lot_size REAL,
                leverage REAL,
                trailing_code TEXT,
                trailing_name TEXT,
                order_type TEXT NOT NULL DEFAULT 'MARKET',
                limit_activated_at TEXT,
                max_entry_deviation_abs REAL,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                closed_at TEXT,
                exit_price REAL,
                result_value REAL,
                result_unit TEXT,
                result_chart_file_id TEXT,
                close_reason TEXT,
                opened_at TEXT,
                holding_seconds INTEGER,
                result_pips REAL,
                cycle_id TEXT
            );

            CREATE TABLE IF NOT EXISTS signal_targets (
                signal_id INTEGER NOT NULL,
                target_no INTEGER NOT NULL,
                price REAL NOT NULL,
                PRIMARY KEY(signal_id, target_no),
                FOREIGN KEY(signal_id) REFERENCES signals(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_signal_targets_signal ON signal_targets(signal_id, target_no);

            CREATE TABLE IF NOT EXISTS signal_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                detail_fa TEXT NOT NULL,
                detail_en TEXT,
                value TEXT,
                free_message_id INTEGER,
                vip_message_id INTEGER,
                admin_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(signal_id) REFERENCES signals(id)
            );

            CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
            CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals(created_at);
            CREATE INDEX IF NOT EXISTS idx_signal_updates_signal ON signal_updates(signal_id);


            CREATE TABLE IF NOT EXISTS subscription_plans (
                code TEXT PRIMARY KEY,
                days INTEGER NOT NULL,
                title_fa TEXT NOT NULL,
                title_en TEXT NOT NULL,
                irr_price TEXT NOT NULL,
                usdt_price TEXT NOT NULL DEFAULT 'SET_PRICE',
                vip_access INTEGER NOT NULL DEFAULT 1,
                autotrade_access INTEGER NOT NULL DEFAULT 1,
                renewal_discount_percent REAL NOT NULL DEFAULT 0,
                upgrade_rank INTEGER NOT NULL DEFAULT 10,
                active INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 100,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_subscription_plans_active ON subscription_plans(active, sort_order);

            CREATE TABLE IF NOT EXISTS autotrade_mt5_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL UNIQUE,
                account_number TEXT NOT NULL UNIQUE,
                broker TEXT,
                server TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                ea_version TEXT,
                bound_at TEXT NOT NULL,
                last_seen_at TEXT,
                FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS autotrade_account_change_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                license_id INTEGER,
                old_account_number TEXT NOT NULL,
                new_account_number TEXT NOT NULL,
                broker TEXT,
                server TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING',
                requested_at TEXT NOT NULL,
                reviewed_at TEXT,
                reviewed_by INTEGER,
                reason TEXT,
                UNIQUE(telegram_id, new_account_number, status),
                FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
            );

            CREATE INDEX IF NOT EXISTS idx_autotrade_account_change_status
                ON autotrade_account_change_requests(status, requested_at);

            CREATE TABLE IF NOT EXISTS autotrade_mt5_account_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                account_number TEXT NOT NULL,
                broker TEXT,
                server TEXT,
                status TEXT NOT NULL,
                valid_from TEXT NOT NULL,
                valid_to TEXT,
                change_request_id INTEGER,
                changed_by INTEGER,
                reason TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_mt5_account_history_user ON autotrade_mt5_account_history(telegram_id, valid_from);

            CREATE TABLE IF NOT EXISTS autotrade_exchange_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL UNIQUE,
                exchange TEXT NOT NULL,
                api_key_enc TEXT,
                api_secret_enc TEXT,
                api_passphrase_enc TEXT,
                account_label TEXT,
                status TEXT NOT NULL DEFAULT 'not_connected',
                bound_at TEXT NOT NULL,
                last_seen_at TEXT,
                FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS autotrade_commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER NOT NULL,
                command TEXT NOT NULL,
                payload_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(signal_id) REFERENCES signals(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_autotrade_commands_signal ON autotrade_commands(signal_id,id);

            CREATE TABLE IF NOT EXISTS autotrade_command_receipts (
                command_id INTEGER NOT NULL,
                telegram_id INTEGER NOT NULL,
                platform TEXT NOT NULL DEFAULT 'MT5',
                status TEXT NOT NULL DEFAULT 'received',
                received_at TEXT NOT NULL,
                executed_at TEXT,
                error_text TEXT,
                PRIMARY KEY(command_id, telegram_id, platform),
                FOREIGN KEY(command_id) REFERENCES autotrade_commands(id) ON DELETE CASCADE,
                FOREIGN KEY(telegram_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS autotrade_signal_receipts (
                signal_id INTEGER NOT NULL,
                telegram_id INTEGER NOT NULL,
                platform TEXT NOT NULL DEFAULT 'MT5',
                status TEXT NOT NULL DEFAULT 'seen',
                first_seen_at TEXT NOT NULL,
                executed_at TEXT,
                ticket TEXT,
                error_text TEXT,
                PRIMARY KEY(signal_id, telegram_id, platform),
                FOREIGN KEY(signal_id) REFERENCES signals(id) ON DELETE CASCADE,
                FOREIGN KEY(telegram_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS autotrade_trade_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                signal_id INTEGER,
                ticket TEXT NOT NULL,
                event_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                destination TEXT NOT NULL DEFAULT 'BOTH',
                symbol TEXT,
                direction TEXT,
                volume REAL,
                entry_price REAL,
                stop_loss REAL,
                take_profit REAL,
                exit_price REAL,
                profit REAL,
                gross_profit REAL NOT NULL DEFAULT 0,
                commission REAL NOT NULL DEFAULT 0,
                swap REAL NOT NULL DEFAULT 0,
                slippage REAL NOT NULL DEFAULT 0,
                risk_cash REAL NOT NULL DEFAULT 0,
                realized_r REAL,
                position_id TEXT,
                deal_id TEXT,
                cycle_id TEXT,
                status TEXT NOT NULL DEFAULT 'RECEIVED',
                error_text TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(telegram_id, ticket, event_id),
                FOREIGN KEY(signal_id) REFERENCES signals(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_trade_exec_user_time
                ON autotrade_trade_executions(telegram_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_trade_exec_ticket
                ON autotrade_trade_executions(telegram_id, ticket, created_at);
            CREATE INDEX IF NOT EXISTS idx_trade_exec_signal
                ON autotrade_trade_executions(signal_id, created_at);

            CREATE TABLE IF NOT EXISTS autotrade_publish_claims (
                signal_id INTEGER NOT NULL,
                channel TEXT NOT NULL,
                claimed_at TEXT NOT NULL,
                PRIMARY KEY(signal_id, channel),
                FOREIGN KEY(signal_id) REFERENCES signals(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS mt5_signal_publication_assets (
                signal_id INTEGER PRIMARY KEY,
                file_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(signal_id) REFERENCES signals(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS autotrade_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                event_key TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                signal_id INTEGER,
                command_id INTEGER,
                payload_json TEXT,
                created_at TEXT NOT NULL,
                sent_at TEXT,
                claimed_at TEXT,
                FOREIGN KEY(telegram_id) REFERENCES users(telegram_id)
            );
            CREATE INDEX IF NOT EXISTS idx_autotrade_notifications_pending ON autotrade_notifications(sent_at,id);

            CREATE TABLE IF NOT EXISTS autotrade_sessions (
                telegram_id INTEGER NOT NULL,
                platform TEXT NOT NULL DEFAULT 'MT5',
                account_number TEXT,
                ea_version TEXT,
                last_ping_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'online',
                PRIMARY KEY(telegram_id, platform),
                FOREIGN KEY(telegram_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS report_dispatches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_type TEXT NOT NULL,
                period_key TEXT NOT NULL,
                recipient_id INTEGER NOT NULL,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                UNIQUE(report_type, period_key, recipient_id)
            );

            CREATE INDEX IF NOT EXISTS idx_report_dispatches_period ON report_dispatches(report_type, period_key);

            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                service_type TEXT NOT NULL CHECK(service_type IN ('signal','auto_trade')),
                duration_days INTEGER NOT NULL,
                price_usdt NUMERIC NOT NULL,
                setup_fee_usdt NUMERIC NOT NULL DEFAULT 0,
                setup_fee_discount_percent REAL NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plan_id INTEGER NOT NULL,
                service_type TEXT NOT NULL,
                starts_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                payment_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(telegram_id),
                FOREIGN KEY(plan_id) REFERENCES plans(id),
                FOREIGN KEY(payment_id) REFERENCES payments(id)
            );
            CREATE INDEX IF NOT EXISTS idx_subscriptions_user_status ON subscriptions(user_id,status,expires_at);

            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plan_id INTEGER NOT NULL,
                invoice_type TEXT NOT NULL,
                payment_method TEXT NOT NULL CHECK(payment_method IN ('usdt','rial')),
                base_amount_usdt NUMERIC NOT NULL,
                usdt_rial_rate NUMERIC,
                final_amount_rial INTEGER,
                wallet_network TEXT,
                wallet_address TEXT,
                payment_status TEXT NOT NULL DEFAULT 'pending',
                expires_at TEXT NOT NULL,
                paid_at TEXT,
                transaction_hash TEXT,
                quote_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(telegram_id),
                FOREIGN KEY(plan_id) REFERENCES plans(id)
            );
            CREATE INDEX IF NOT EXISTS idx_invoices_user_status ON invoices(user_id,payment_status,expires_at);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_invoices_tx_hash_ci ON invoices(LOWER(transaction_hash)) WHERE transaction_hash IS NOT NULL AND transaction_hash<>'';
            """
        )

        # Safe migrations from earlier versions.
        ucols = _columns(con, "users")
        for name, ddl in [
            ("language", "ALTER TABLE users ADD COLUMN language TEXT"),
            ("referral_code", "ALTER TABLE users ADD COLUMN referral_code TEXT"),
            ("referred_by", "ALTER TABLE users ADD COLUMN referred_by INTEGER"),
            ("points_balance", "ALTER TABLE users ADD COLUMN points_balance INTEGER NOT NULL DEFAULT 0"),
            ("referral_rewarded", "ALTER TABLE users ADD COLUMN referral_rewarded INTEGER NOT NULL DEFAULT 0"),
        ]:
            if name not in ucols:
                con.execute(ddl)
        try:
            con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_referral_code ON users(referral_code) WHERE referral_code IS NOT NULL")
        except sqlite3.OperationalError:
            pass

        scols = _columns(con, "signals")
        if "volume_mode" not in scols:
            con.execute("ALTER TABLE signals ADD COLUMN volume_mode TEXT NOT NULL DEFAULT 'RISK'")

        ncols = _columns(con, "autotrade_notifications")
        if "claimed_at" not in ncols:
            con.execute("ALTER TABLE autotrade_notifications ADD COLUMN claimed_at TEXT")

        pcols = _columns(con, "payments")
        migrations = {
            "payment_method": "ALTER TABLE payments ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'irr'",
            "base_amount_irr": "ALTER TABLE payments ADD COLUMN base_amount_irr INTEGER",
            "final_amount_irr": "ALTER TABLE payments ADD COLUMN final_amount_irr INTEGER",
            "discount_percent": "ALTER TABLE payments ADD COLUMN discount_percent REAL NOT NULL DEFAULT 0",
            "promo_code": "ALTER TABLE payments ADD COLUMN promo_code TEXT",
            "points_used": "ALTER TABLE payments ADD COLUMN points_used INTEGER NOT NULL DEFAULT 0",
            "receipt_message_id": "ALTER TABLE payments ADD COLUMN receipt_message_id INTEGER",
            "txid": "ALTER TABLE payments ADD COLUMN txid TEXT",
            "campaign_id": "ALTER TABLE payments ADD COLUMN campaign_id INTEGER",
            "invoice_id": "ALTER TABLE payments ADD COLUMN invoice_id INTEGER",
            "amount_usdt": "ALTER TABLE payments ADD COLUMN amount_usdt NUMERIC",
            "amount_rial": "ALTER TABLE payments ADD COLUMN amount_rial INTEGER",
            "transaction_hash": "ALTER TABLE payments ADD COLUMN transaction_hash TEXT",
            "payment_reference": "ALTER TABLE payments ADD COLUMN payment_reference TEXT",
            "verified_by": "ALTER TABLE payments ADD COLUMN verified_by INTEGER",
            "verified_at": "ALTER TABLE payments ADD COLUMN verified_at TEXT",
        }
        for name, ddl in migrations.items():
            if name not in pcols:
                con.execute(ddl)
        try:
            con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_txid_unique ON payments(txid) WHERE txid IS NOT NULL AND txid<>''")
        except sqlite3.OperationalError:
            pass

        scols = _columns(con, "signals")
        signal_migrations = {
            "trailing_config_json": "ALTER TABLE signals ADD COLUMN trailing_config_json TEXT",
            "max_entry_deviation_pct": "ALTER TABLE signals ADD COLUMN max_entry_deviation_pct REAL",
            "lot_size": "ALTER TABLE signals ADD COLUMN lot_size REAL",
            "leverage": "ALTER TABLE signals ADD COLUMN leverage REAL",
            "trailing_code": "ALTER TABLE signals ADD COLUMN trailing_code TEXT",
            "trailing_name": "ALTER TABLE signals ADD COLUMN trailing_name TEXT",
            "publish_token": "ALTER TABLE signals ADD COLUMN publish_token TEXT",
            "order_type": "ALTER TABLE signals ADD COLUMN order_type TEXT NOT NULL DEFAULT 'MARKET'",
            "stop_limit_price": "ALTER TABLE signals ADD COLUMN stop_limit_price REAL",
            "limit_activated_at": "ALTER TABLE signals ADD COLUMN limit_activated_at TEXT",
            "max_entry_deviation_abs": "ALTER TABLE signals ADD COLUMN max_entry_deviation_abs REAL",
            "timeframe": "ALTER TABLE signals ADD COLUMN timeframe TEXT NOT NULL DEFAULT 'M5'",
            "close_reason": "ALTER TABLE signals ADD COLUMN close_reason TEXT",
            "opened_at": "ALTER TABLE signals ADD COLUMN opened_at TEXT",
            "holding_seconds": "ALTER TABLE signals ADD COLUMN holding_seconds INTEGER",
            "result_pips": "ALTER TABLE signals ADD COLUMN result_pips REAL",
        }
        for name, ddl in signal_migrations.items():
            if name not in scols:
                con.execute(ddl)
        # Unified reporting / execution truth migrations.
        scols = _columns(con, "signals")
        if "cycle_id" not in scols:
            con.execute("ALTER TABLE signals ADD COLUMN cycle_id TEXT")
        # v0.6.0: MT5 is the sole signal authority. These fields make issuer
        # identity immutable/auditable without breaking legacy rows.
        scols = _columns(con, "signals")
        authority_migrations = {
            "signal_uuid": "ALTER TABLE signals ADD COLUMN signal_uuid TEXT",
            "revision": "ALTER TABLE signals ADD COLUMN revision INTEGER NOT NULL DEFAULT 1",
            "issuer_type": "ALTER TABLE signals ADD COLUMN issuer_type TEXT NOT NULL DEFAULT 'LEGACY_TELEGRAM'",
            "issuer_account": "ALTER TABLE signals ADD COLUMN issuer_account TEXT",
            "issued_at": "ALTER TABLE signals ADD COLUMN issued_at TEXT",
        }
        for name, ddl in authority_migrations.items():
            if name not in scols:
                con.execute(ddl)
        con.execute("UPDATE signals SET revision=COALESCE(revision,1), issuer_type=COALESCE(NULLIF(issuer_type,''),'LEGACY_TELEGRAM')")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_signals_uuid ON signals(signal_uuid) WHERE signal_uuid IS NOT NULL AND signal_uuid<>''")
        con.execute("CREATE INDEX IF NOT EXISTS idx_signals_authority ON signals(issuer_type,issuer_account,created_at)")
        con.execute("""
            CREATE TABLE IF NOT EXISTS signal_events_v060 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER NOT NULL,
                signal_uuid TEXT,
                revision INTEGER NOT NULL DEFAULT 1,
                event_type TEXT NOT NULL,
                actor_type TEXT NOT NULL,
                actor_id TEXT,
                account_number TEXT,
                event_time TEXT NOT NULL,
                request_id TEXT,
                correlation_id TEXT,
                result TEXT NOT NULL DEFAULT 'SUCCESS',
                reason TEXT,
                payload_json TEXT,
                FOREIGN KEY(signal_id) REFERENCES signals(id) ON DELETE CASCADE
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_signal_events_signal ON signal_events_v060(signal_id,id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_signal_events_correlation ON signal_events_v060(correlation_id)")
        con.execute("""
            CREATE TABLE IF NOT EXISTS signal_deliveries_v060 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER NOT NULL,
                signal_uuid TEXT,
                account_number TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                processed_at TEXT,
                status TEXT NOT NULL DEFAULT 'RECEIVED',
                ticket TEXT,
                error_text TEXT,
                UNIQUE(signal_id,account_number),
                FOREIGN KEY(signal_id) REFERENCES signals(id) ON DELETE CASCADE
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_signal_deliveries_account ON signal_deliveries_v060(account_number,status)")
        con.execute("""
            CREATE TABLE IF NOT EXISTS mt5_heartbeats_v060 (
                account_number TEXT PRIMARY KEY,
                role TEXT NOT NULL DEFAULT 'CLIENT',
                ea_version TEXT,
                last_seen_at TEXT NOT NULL,
                payload_json TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS mt5_live_state (
                account_number TEXT NOT NULL,
                state_type TEXT NOT NULL,
                identifier TEXT NOT NULL,
                ticket TEXT NOT NULL,
                signal_code TEXT,
                symbol TEXT NOT NULL,
                direction TEXT,
                volume REAL NOT NULL DEFAULT 0,
                entry_price REAL NOT NULL DEFAULT 0,
                current_price REAL NOT NULL DEFAULT 0,
                stop_loss REAL NOT NULL DEFAULT 0,
                take_profit REAL NOT NULL DEFAULT 0,
                profit REAL NOT NULL DEFAULT 0,
                magic INTEGER NOT NULL DEFAULT 0,
                nexus_managed INTEGER NOT NULL DEFAULT 0,
                order_type TEXT,
                status TEXT NOT NULL DEFAULT 'OPEN',
                broker TEXT,
                server TEXT,
                last_seen_at TEXT NOT NULL,
                PRIMARY KEY(account_number,state_type,identifier)
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_mt5_live_account_status ON mt5_live_state(account_number,status,last_seen_at)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_mt5_live_signal ON mt5_live_state(account_number,signal_code,status)")
        ecols = _columns(con, "autotrade_trade_executions")
        execution_migrations = {
            "gross_profit": "ALTER TABLE autotrade_trade_executions ADD COLUMN gross_profit REAL NOT NULL DEFAULT 0",
            "commission": "ALTER TABLE autotrade_trade_executions ADD COLUMN commission REAL NOT NULL DEFAULT 0",
            "swap": "ALTER TABLE autotrade_trade_executions ADD COLUMN swap REAL NOT NULL DEFAULT 0",
            "slippage": "ALTER TABLE autotrade_trade_executions ADD COLUMN slippage REAL NOT NULL DEFAULT 0",
            "risk_cash": "ALTER TABLE autotrade_trade_executions ADD COLUMN risk_cash REAL NOT NULL DEFAULT 0",
            "realized_r": "ALTER TABLE autotrade_trade_executions ADD COLUMN realized_r REAL",
            "position_id": "ALTER TABLE autotrade_trade_executions ADD COLUMN position_id TEXT",
            "deal_id": "ALTER TABLE autotrade_trade_executions ADD COLUMN deal_id TEXT",
            "cycle_id": "ALTER TABLE autotrade_trade_executions ADD COLUMN cycle_id TEXT",
        }
        for name, ddl in execution_migrations.items():
            if name not in ecols:
                con.execute(ddl)
        con.execute("CREATE INDEX IF NOT EXISTS idx_trade_exec_position ON autotrade_trade_executions(telegram_id, position_id, created_at)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_trade_exec_cycle ON autotrade_trade_executions(telegram_id, cycle_id, created_at)")
        current_cycle = get_setting("current_cycle_id", "CYCLE-LEGACY", con=con)
        con.execute("UPDATE signals SET cycle_id=COALESCE(NULLIF(cycle_id,''),?)", (current_cycle,))
        con.execute("UPDATE autotrade_trade_executions SET cycle_id=COALESCE(NULLIF(cycle_id,''),?)", (current_cycle,))
        try:
            con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_signals_publish_token ON signals(publish_token) WHERE publish_token IS NOT NULL")
        except sqlite3.OperationalError:
            pass

        # Subscription / license engine v7 migrations. Defaults preserve v6 behavior:
        # any existing active license keeps both VIP and Auto Trade access.
        lcols = _columns(con, "licenses")
        license_migrations = {
            "subscription_id": "ALTER TABLE licenses ADD COLUMN subscription_id INTEGER",
            "license_key": "ALTER TABLE licenses ADD COLUMN license_key TEXT",
            "plan_code": "ALTER TABLE licenses ADD COLUMN plan_code TEXT",
            "source": "ALTER TABLE licenses ADD COLUMN source TEXT NOT NULL DEFAULT 'payment'",
            "vip_access": "ALTER TABLE licenses ADD COLUMN vip_access INTEGER NOT NULL DEFAULT 1",
            "autotrade_access": "ALTER TABLE licenses ADD COLUMN autotrade_access INTEGER NOT NULL DEFAULT 1",
            "granted_by": "ALTER TABLE licenses ADD COLUMN granted_by INTEGER",
            "vip_expires_at": "ALTER TABLE licenses ADD COLUMN vip_expires_at TEXT",
            "autotrade_expires_at": "ALTER TABLE licenses ADD COLUMN autotrade_expires_at TEXT",
        }
        for name, ddl in license_migrations.items():
            if name not in lcols:
                con.execute(ddl)
        con.execute("UPDATE licenses SET vip_expires_at=expires_at WHERE vip_expires_at IS NULL AND vip_access=1")
        con.execute("UPDATE licenses SET autotrade_expires_at=expires_at WHERE autotrade_expires_at IS NULL AND autotrade_access=1")
        con.execute("CREATE INDEX IF NOT EXISTS idx_licenses_license_key ON licenses(license_key)")
        # Keep one live row per issued key; legacy duplicates are normalized before the unique index.
        dupes = con.execute("SELECT license_key, MAX(id) AS keep_id FROM licenses WHERE license_key IS NOT NULL GROUP BY license_key HAVING COUNT(*)>1").fetchall()
        for d in dupes:
            con.execute("UPDATE licenses SET license_key=NULL WHERE license_key=? AND id<>?", (d["license_key"], int(d["keep_id"])))
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_licenses_license_key_unique ON licenses(license_key) WHERE license_key IS NOT NULL")
        # Backfill every legacy NULL key with a unique fresh key.
        rows = con.execute("SELECT id,license_key FROM licenses WHERE license_key IS NULL ORDER BY id").fetchall()
        for row in rows:
            con.execute("UPDATE licenses SET license_key=? WHERE id=?", (_new_license_key(), int(row["id"])))

        plancols = _columns(con, "subscription_plans")
        plan_migrations = {
            "vip_access": "ALTER TABLE subscription_plans ADD COLUMN vip_access INTEGER NOT NULL DEFAULT 1",
            "autotrade_access": "ALTER TABLE subscription_plans ADD COLUMN autotrade_access INTEGER NOT NULL DEFAULT 1",
            "renewal_discount_percent": "ALTER TABLE subscription_plans ADD COLUMN renewal_discount_percent REAL NOT NULL DEFAULT 0",
            "upgrade_rank": "ALTER TABLE subscription_plans ADD COLUMN upgrade_rank INTEGER NOT NULL DEFAULT 10",
            "service_type": "ALTER TABLE subscription_plans ADD COLUMN service_type TEXT NOT NULL DEFAULT 'signal'",
            "duration_days": "ALTER TABLE subscription_plans ADD COLUMN duration_days INTEGER",
            "price_usdt": "ALTER TABLE subscription_plans ADD COLUMN price_usdt NUMERIC",
            "setup_fee_usdt": "ALTER TABLE subscription_plans ADD COLUMN setup_fee_usdt NUMERIC NOT NULL DEFAULT 0",
            "setup_fee_discount_percent": "ALTER TABLE subscription_plans ADD COLUMN setup_fee_discount_percent REAL NOT NULL DEFAULT 0",
            "is_active": "ALTER TABLE subscription_plans ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1",
        }
        for name, ddl in plan_migrations.items():
            if name not in plancols:
                con.execute(ddl)

        # Backfill legacy TP1/TP2/TP3 rows into the dynamic targets table.
        legacy_signals = con.execute("SELECT id,tp1,tp2,tp3 FROM signals").fetchall()
        for sig in legacy_signals:
            exists = con.execute("SELECT 1 FROM signal_targets WHERE signal_id=? LIMIT 1", (sig["id"],)).fetchone()
            if exists:
                continue
            for idx, price in enumerate((sig["tp1"], sig["tp2"], sig["tp3"]), 1):
                if price is not None:
                    con.execute("INSERT OR IGNORE INTO signal_targets(signal_id,target_no,price) VALUES(?,?,?)", (sig["id"], idx, float(price)))

        defaults = {
            "referral_points_per_success": "100",
            "points_per_percent": "100",
            "max_points_discount_percent": "30",
        }
        for k, v in defaults.items():
            con.execute(
                "INSERT OR IGNORE INTO app_settings(key,value,updated_at) VALUES(?,?,?)",
                (k, v, now_iso()),
            )

        # Normalize legacy payment identifiers and create case-insensitive TXID protection.
        try:
            con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_txid_ci ON payments(LOWER(txid)) WHERE txid IS NOT NULL AND txid<>''")
        except sqlite3.IntegrityError:
            # Legacy duplicates are retained for audit; new inserts are normalized by application code.
            pass
        con.execute("INSERT OR IGNORE INTO app_settings(key,value,updated_at) VALUES('autotrade_expiry_mode','A',?)", (now_iso(),))
        con.execute("INSERT OR IGNORE INTO app_settings(key,value,updated_at) VALUES('upgrade_proration_enabled','true',?)", (now_iso(),))


def _new_referral_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "NX" + "".join(secrets.choice(alphabet) for _ in range(8))


def upsert_user(telegram_id: int, username: str | None, first_name: str | None) -> None:
    now = now_iso()
    with conn() as con:
        con.execute(
            """
            INSERT INTO users(telegram_id, username, first_name, created_at, updated_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(telegram_id) DO UPDATE SET
              username=excluded.username,
              first_name=excluded.first_name,
              updated_at=excluded.updated_at
            """,
            (telegram_id, username, first_name, now, now),
        )
        row = con.execute("SELECT referral_code FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        if row and not row[0]:
            for _ in range(20):
                code = _new_referral_code()
                try:
                    con.execute("UPDATE users SET referral_code=? WHERE telegram_id=?", (code, telegram_id))
                    break
                except sqlite3.IntegrityError:
                    continue


def set_language(telegram_id: int, language: str) -> None:
    with conn() as con:
        con.execute("UPDATE users SET language=?, updated_at=? WHERE telegram_id=?", (language, now_iso(), telegram_id))


def mark_public_joined(telegram_id: int, joined: bool) -> None:
    with conn() as con:
        con.execute("UPDATE users SET joined_public=?, updated_at=? WHERE telegram_id=?", (1 if joined else 0, now_iso(), telegram_id))


def set_last_menu_message(telegram_id: int, message_id: int | None) -> None:
    with conn() as con:
        con.execute("UPDATE users SET last_menu_message_id=?, updated_at=? WHERE telegram_id=?", (message_id, now_iso(), telegram_id))


def get_user(telegram_id: int):
    with conn() as con:
        return con.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()


def get_user_by_referral(code: str):
    with conn() as con:
        return con.execute("SELECT * FROM users WHERE UPPER(referral_code)=UPPER(?)", (code.strip(),)).fetchone()


def set_referred_by(telegram_id: int, referrer_id: int) -> bool:
    if telegram_id == referrer_id:
        return False
    with conn() as con:
        row = con.execute("SELECT referred_by FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        if not row or row[0] is not None:
            return False
        con.execute("UPDATE users SET referred_by=?, updated_at=? WHERE telegram_id=?", (referrer_id, now_iso(), telegram_id))
        return True


def reward_referral_if_ready(referred_id: int) -> tuple[int, int] | None:
    """Reward once after referred user confirms public-channel membership. Returns (referrer_id, points)."""
    with conn() as con:
        user = con.execute("SELECT * FROM users WHERE telegram_id=?", (referred_id,)).fetchone()
        if not user or not user["joined_public"] or user["referral_rewarded"] or not user["referred_by"]:
            return None
        referrer_id = int(user["referred_by"])
        if referrer_id == referred_id:
            return None
        exists = con.execute("SELECT 1 FROM referral_events WHERE referred_id=?", (referred_id,)).fetchone()
        if exists:
            con.execute("UPDATE users SET referral_rewarded=1 WHERE telegram_id=?", (referred_id,))
            return None
        points = int(get_setting("referral_points_per_success", "100", con=con))
        con.execute(
            "INSERT INTO referral_events(referrer_id,referred_id,points,created_at) VALUES(?,?,?,?)",
            (referrer_id, referred_id, points, now_iso()),
        )
        con.execute("UPDATE users SET points_balance=points_balance+?, updated_at=? WHERE telegram_id=?", (points, now_iso(), referrer_id))
        con.execute("UPDATE users SET referral_rewarded=1, updated_at=? WHERE telegram_id=?", (now_iso(), referred_id))
        con.execute(
            "INSERT INTO point_ledger(telegram_id,delta,reason,ref_id,created_at) VALUES(?,?,?,?,?)",
            (referrer_id, points, "referral_reward", str(referred_id), now_iso()),
        )
        return referrer_id, points


def referral_stats(telegram_id: int) -> dict[str, int]:
    with conn() as con:
        invited = con.execute("SELECT COUNT(*) FROM users WHERE referred_by=?", (telegram_id,)).fetchone()[0]
        successful = con.execute("SELECT COUNT(*) FROM referral_events WHERE referrer_id=? AND status='rewarded'", (telegram_id,)).fetchone()[0]
        user = con.execute("SELECT points_balance FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        return {"invited": int(invited), "successful": int(successful), "points": int(user[0] if user else 0)}


def list_users(limit: int = 20):
    with conn() as con:
        return list(con.execute("SELECT * FROM users ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall())


def count_user_payments(telegram_id: int) -> int:
    with conn() as con:
        return int(con.execute("SELECT COUNT(*) FROM payments WHERE telegram_id=? AND status='approved'", (telegram_id,)).fetchone()[0])


def user_paid_license_history(telegram_id: int, limit: int = 10):
    """Paid subscription history with actual license start/end dates."""
    with conn() as con:
        return list(con.execute(
            """
            SELECT l.id AS license_id,l.starts_at,l.expires_at,l.status AS license_status,
                   l.plan_code AS license_plan_code,l.source,l.vip_access,l.autotrade_access,
                   p.id AS payment_id,p.plan_code,p.days,p.price_label,p.final_amount_irr,p.payment_method,p.reviewed_at
            FROM licenses l
            JOIN payments p ON p.id=l.payment_id
            WHERE l.telegram_id=? AND l.payment_id IS NOT NULL AND p.status='approved'
            ORDER BY l.id DESC LIMIT ?
            """, (telegram_id, limit)
        ).fetchall())


def plan_dict(row) -> dict[str, object]:
    if not row:
        return {}
    return {
        "id": int(row["canonical_plan_id"]) if "canonical_plan_id" in row.keys() and row["canonical_plan_id"] is not None else (int(row["id"]) if "id" in row.keys() else None),
        "code": str(row["code"]),
        "name": str(row["title_fa"] if "title_fa" in row.keys() else row["name"]),
        "fa": str(row["title_fa"] if "title_fa" in row.keys() else row["name"]),
        "en": str(row["title_en"] if "title_en" in row.keys() else row["name"]),
        "service_type": str(row["canonical_service_type"] or row["service_type"] or ("auto_trade" if "autotrade_access" in row.keys() and row["autotrade_access"] else "signal")),
        "days": int(row["canonical_duration_days"] or row["duration_days"] or row["days"]),
        "duration_days": int(row["canonical_duration_days"] or row["duration_days"] or row["days"]),
        "usdt": str(row["canonical_price_usdt"] if "canonical_price_usdt" in row.keys() and row["canonical_price_usdt"] is not None else (row["price_usdt"] if "price_usdt" in row.keys() and row["price_usdt"] is not None else row["usdt_price"])),
        "price_usdt": str(row["canonical_price_usdt"] if "canonical_price_usdt" in row.keys() and row["canonical_price_usdt"] is not None else (row["price_usdt"] if "price_usdt" in row.keys() and row["price_usdt"] is not None else row["usdt_price"])),
        "setup_fee_usdt": str(row["canonical_setup_fee_usdt"] if "canonical_setup_fee_usdt" in row.keys() and row["canonical_setup_fee_usdt"] is not None else (row["setup_fee_usdt"] if "setup_fee_usdt" in row.keys() else 0)),
        "setup_fee_discount_percent": float(row["canonical_setup_fee_discount_percent"] if "canonical_setup_fee_discount_percent" in row.keys() and row["canonical_setup_fee_discount_percent"] is not None else (row["setup_fee_discount_percent"] if "setup_fee_discount_percent" in row.keys() else 0)),
        "vip_access": bool(row["vip_access"]) if "vip_access" in row.keys() else str(row["service_type"]) == "auto_trade",
        "autotrade_access": bool(row["autotrade_access"]) if "autotrade_access" in row.keys() else str(row["service_type"]) == "auto_trade",
        "active": bool(row["active"] if "active" in row.keys() else row["is_active"]),
        "renewal_discount_percent": float(row["renewal_discount_percent"] or 0) if "renewal_discount_percent" in row.keys() else 0.0,
        "upgrade_rank": int(row["upgrade_rank"] or 10) if "upgrade_rank" in row.keys() else 10,
    }


def current_entitlements(telegram_id: int) -> dict[str, object]:
    lic = active_license(telegram_id)
    if not lic:
        return {"active": False, "vip": False, "autotrade": False, "plan_code": None, "vip_expires_at": None, "autotrade_expires_at": None}
    return {
        "active": True,
        "vip": has_entitlement(telegram_id, "vip"),
        "autotrade": has_entitlement(telegram_id, "autotrade"),
        "plan_code": str(lic["plan_code"]) if lic["plan_code"] else None,
        "vip_expires_at": str(lic["vip_expires_at"]) if lic["vip_expires_at"] else None,
        "autotrade_expires_at": str(lic["autotrade_expires_at"]) if lic["autotrade_expires_at"] else None,
    }


def create_invoice(*, user_id: int, plan_id: int, invoice_type: str, payment_method: str, base_amount_usdt, usdt_rial_rate, final_amount_rial, wallet_network, wallet_address, expires_at: str, quote_json: str | None = None) -> int:
    with conn() as con:
        cur = con.execute(
            """INSERT INTO invoices(user_id,plan_id,invoice_type,payment_method,base_amount_usdt,usdt_rial_rate,final_amount_rial,
               wallet_network,wallet_address,payment_status,expires_at,quote_json,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,'pending',?,?,?,?)""",
            (user_id,plan_id,invoice_type,payment_method,str(base_amount_usdt),str(usdt_rial_rate) if usdt_rial_rate is not None else None,
             final_amount_rial,wallet_network,wallet_address,expires_at,quote_json,now_iso(),now_iso()),
        )
        return int(cur.lastrowid)


def get_invoice(invoice_id: int):
    with conn() as con:
        return con.execute("SELECT i.*, p.code, p.duration_days AS days, p.name AS title_en, p.name AS title_fa, p.price_usdt, p.service_type, p.setup_fee_usdt FROM invoices i JOIN plans p ON p.id=i.plan_id WHERE i.id=?", (invoice_id,)).fetchone()


def expire_old_invoices() -> int:
    with conn() as con:
        cur = con.execute("UPDATE invoices SET payment_status='expired',updated_at=? WHERE payment_status='pending' AND expires_at<=?", (now_iso(), now_iso()))
        return cur.rowcount


def mark_invoice_paid(invoice_id: int, tx_hash: str | None = None) -> bool:
    with conn() as con:
        cur = con.execute("UPDATE invoices SET payment_status='paid',paid_at=?,transaction_hash=?,updated_at=? WHERE id=? AND payment_status='pending' AND expires_at>?", (now_iso(), (tx_hash or '').strip().lower() or None, now_iso(), invoice_id, now_iso()))
        return cur.rowcount == 1


def cancel_invoice(invoice_id: int) -> None:
    with conn() as con:
        con.execute("UPDATE invoices SET payment_status='cancelled',updated_at=? WHERE id=? AND payment_status='pending'", (now_iso(), invoice_id))


def create_payment(
    telegram_id: int,
    plan_code: str,
    days: int,
    price_label: str,
    payment_method: str,
    receipt_file_id: str,
    receipt_type: str,
    receipt_message_id: int | None = None,
    base_amount_irr: int | None = None,
    final_amount_irr: int | None = None,
    discount_percent: float = 0,
    promo_code: str | None = None,
    points_used: int = 0,
    txid: str | None = None,
    campaign_id: int | None = None,
    invoice_id: int | None = None,
    amount_usdt: float | str | None = None,
    amount_rial: int | None = None,
    transaction_hash: str | None = None,
    payment_reference: str | None = None,
) -> int:
    normalized_txid = str(transaction_hash or txid or "").strip().lower() or None
    if normalized_txid and txid_exists(normalized_txid):
        raise ValueError("transaction hash has already been used")
    with conn() as con:
        cur = con.execute(
            """
            INSERT INTO payments(
              telegram_id,plan_code,days,price_label,payment_method,receipt_file_id,receipt_type,
              receipt_message_id,base_amount_irr,final_amount_irr,discount_percent,promo_code,points_used,txid,campaign_id,
              invoice_id,amount_usdt,amount_rial,transaction_hash,payment_reference,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                telegram_id, plan_code, days, price_label, payment_method, receipt_file_id, receipt_type,
                receipt_message_id, base_amount_irr, final_amount_irr, discount_percent, promo_code, points_used, normalized_txid, campaign_id,
                invoice_id, amount_usdt, amount_rial, normalized_txid, payment_reference, now_iso(),
            ),
        )
        return int(cur.lastrowid)


def cancel_payment_reservation(payment_id: int, *, refund_points_balance: bool = True) -> None:
    with conn() as con:
        pay = con.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
    if not pay or str(pay["status"]) != "pending":
        return
    if refund_points_balance and int(pay["points_used"] or 0):
        refund_points(int(pay["telegram_id"]), int(pay["points_used"]), "payment_reservation_cancel", str(payment_id))
    release_discount_use(payment_id)
    release_campaign_use(payment_id)
    with conn() as con:
        con.execute("UPDATE payments SET status='cancelled',admin_note='reservation rollback',reviewed_at=? WHERE id=? AND status='pending'", (now_iso(),payment_id))
        if pay["invoice_id"]:
            con.execute("UPDATE invoices SET payment_status='cancelled',updated_at=? WHERE id=? AND payment_status='pending'", (now_iso(),pay["invoice_id"]))


def user_payments(telegram_id: int, status: str = "all", limit: int = 30):
    """Return the user's payment history without exposing admin-only fields."""
    status = str(status or "all").lower().strip()
    where = "WHERE telegram_id=?"
    args: list[object] = [telegram_id]
    if status == "approved":
        where += " AND status='approved'"
    elif status == "pending":
        where += " AND status='pending'"
    elif status == "failed":
        where += " AND status IN ('rejected','cancelled','failed')"
    elif status != "all":
        raise ValueError("invalid payment status")
    with conn() as con:
        return list(con.execute(
            f"""SELECT id,plan_code,days,payment_method,status,amount_usdt,amount_rial,
                       final_amount_irr,created_at,reviewed_at,invoice_id
                FROM payments {where}
                ORDER BY id DESC LIMIT ?""",
            (*args, max(1, min(int(limit), 100))),
        ).fetchall())


def get_payment(payment_id: int):
    with conn() as con:
        return con.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()


def list_pending_payments(limit: int = 30):
    with conn() as con:
        return list(con.execute("SELECT * FROM payments WHERE status='pending' ORDER BY created_at ASC LIMIT ?", (limit,)).fetchall())


def review_payment(payment_id: int, status: str, admin_id: int, note: str | None = None) -> bool:
    with conn() as con:
        pay = con.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
        if not pay or str(pay["status"]) != "pending":
            return False
        if str(status).lower() == "approved" and pay["invoice_id"]:
            inv = con.execute("SELECT payment_status,expires_at FROM invoices WHERE id=?", (pay["invoice_id"],)).fetchone()
            if not inv or str(inv["payment_status"]) != "pending" or str(inv["expires_at"]) <= now_iso():
                return False
            con.execute("UPDATE invoices SET payment_status='paid',paid_at=?,transaction_hash=COALESCE(?,transaction_hash),updated_at=? WHERE id=?", (now_iso(), pay["transaction_hash"], now_iso(), pay["invoice_id"]))
        if str(status).lower() in {"rejected","cancelled"} and pay["invoice_id"]:
            con.execute("UPDATE invoices SET payment_status='cancelled',updated_at=? WHERE id=? AND payment_status='pending'", (now_iso(), pay["invoice_id"]))
        cur = con.execute(
            "UPDATE payments SET status=?, admin_id=?, admin_note=?, reviewed_at=?, verified_by=?, verified_at=? WHERE id=? AND status='pending'",
            (status, admin_id, note, now_iso(), admin_id if str(status).lower() in {"approved","rejected"} else None, now_iso() if str(status).lower() in {"approved","rejected"} else None, payment_id),
        )
        return cur.rowcount == 1


def active_license(telegram_id: int):
    now=now_iso()
    with conn() as con:
        return con.execute(
            """SELECT * FROM licenses WHERE telegram_id=? AND status='active'
               AND COALESCE(MAX(COALESCE(vip_expires_at,''),COALESCE(autotrade_expires_at,'')),expires_at)>?
               ORDER BY id DESC LIMIT 1""",
            (telegram_id, now),
        ).fetchone()

def latest_license(telegram_id: int):
    with conn() as con:
        return con.execute("SELECT * FROM licenses WHERE telegram_id=? ORDER BY id DESC LIMIT 1", (telegram_id,)).fetchone()


def _new_license_key() -> str:
    # 128 bits of randomness encoded as 26 URL-safe characters. The key remains
    # human-copyable while being infeasible to brute-force online.
    return "NXS-" + secrets.token_urlsafe(16).replace("-", "").replace("_", "").upper()[:22]


def license_by_key(license_key: str, *, active_only: bool = False):
    key = str(license_key or "").strip().upper()
    if not key:
        return None
    sql = "SELECT * FROM licenses WHERE license_key=?"
    args = [key]
    if active_only:
        sql += " AND status='active' AND COALESCE(MAX(COALESCE(vip_expires_at,''),COALESCE(autotrade_expires_at,'')),expires_at)>?"
        args.append(now_iso())
    sql += " ORDER BY id DESC LIMIT 1"
    with conn() as con:
        return con.execute(sql, tuple(args)).fetchone()

def create_or_extend_license(
    telegram_id: int,
    payment_id: int | None,
    days: int,
    *,
    plan_code: str | None = None,
    source: str | None = None,
    vip_access: bool | None = None,
    autotrade_access: bool | None = None,
    granted_by: int | None = None,
):
    """Create/renew entitlement-aware access. VIP and Auto Trade expire independently."""
    if days <= 0:
        raise ValueError("license days must be positive")
    now_dt = datetime.now(timezone.utc)
    current = active_license(telegram_id)
    previous = latest_license(telegram_id)
    # Every newly issued/superseding license gets a fresh key. This preserves
    # uniqueness and prevents an old key from remaining valid by accident.
    license_key=_new_license_key()

    plan=get_plan(str(plan_code)) if plan_code else None
    if vip_access is None:
        vip_access=bool(plan["vip_access"]) if plan and "vip_access" in plan.keys() else True
    if autotrade_access is None:
        autotrade_access=bool(plan["autotrade_access"]) if plan and "autotrade_access" in plan.keys() else True

    def parse_exp(row, key):
        if not row: return None
        raw=row[key] if key in row.keys() else None
        if not raw: return None
        try: return datetime.fromisoformat(str(raw))
        except Exception: return None

    old_vip=parse_exp(current,"vip_expires_at") or (parse_exp(current,"expires_at") if current and bool(current["vip_access"]) else None)
    old_auto=parse_exp(current,"autotrade_expires_at") or (parse_exp(current,"expires_at") if current and bool(current["autotrade_access"]) else None)
    vip_exp=old_vip
    auto_exp=old_auto
    upgrading_vip_to_auto = bool(autotrade_access) and bool(vip_access) and bool(current) and not bool(current["autotrade_access"])
    if upgrading_vip_to_auto:
        # Preserve the remaining VIP time, then append the new Auto Trade term.
        base = old_vip if old_vip and old_vip > now_dt else now_dt
        new_exp = base + timedelta(days=days)
        vip_exp = new_exp
        auto_exp = new_exp
    else:
        if bool(vip_access):
            base=old_vip if old_vip and old_vip>now_dt else now_dt
            vip_exp=base+timedelta(days=days)
        if bool(autotrade_access):
            base=old_auto if old_auto and old_auto>now_dt else now_dt
            auto_exp=base+timedelta(days=days)

    # Existing entitlements are preserved until their own expiry.
    vip_flag=bool(vip_exp and vip_exp>now_dt)
    auto_flag=bool(auto_exp and auto_exp>now_dt)
    overall=max([d for d in (vip_exp,auto_exp) if d is not None], default=now_dt)
    starts=now_dt
    if current:
        try: starts=datetime.fromisoformat(str(current["starts_at"]))
        except Exception: pass
    if source is None:
        source="payment" if payment_id is not None else "admin"
    with conn() as con:
        if current:
            con.execute("UPDATE licenses SET status='superseded' WHERE id=?", (current["id"],))
        subscription_id = None
        canonical_plan_id = None
        service_type = "auto_trade" if bool(autotrade_access) else "signal"
        if plan_code:
            prow = con.execute("SELECT id,service_type FROM plans WHERE code=?", (str(plan_code),)).fetchone()
            if prow:
                canonical_plan_id = int(prow["id"])
                service_type = str(prow["service_type"])
        if canonical_plan_id is not None:
            sub_cur = con.execute(
                """INSERT INTO subscriptions(user_id,plan_id,service_type,starts_at,expires_at,status,payment_id,created_at,updated_at)
                   VALUES(?,?,?,?,?,'active',?,?,?)""",
                (telegram_id,canonical_plan_id,service_type,starts.isoformat(),overall.isoformat(),payment_id,now_iso(),now_iso()),
            )
            subscription_id = int(sub_cur.lastrowid)
        cur=con.execute(
            """INSERT INTO licenses(telegram_id,payment_id,license_key,plan_code,source,vip_access,autotrade_access,granted_by,
                                      starts_at,expires_at,vip_expires_at,autotrade_expires_at,status,created_at,subscription_id)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?, 'active', ?, ?)""",
            (telegram_id,payment_id,license_key,plan_code,source,1 if vip_flag else 0,1 if auto_flag else 0,granted_by,
             starts.isoformat(),overall.isoformat(),vip_exp.isoformat() if vip_exp else None,auto_exp.isoformat() if auto_exp else None,now_iso(),subscription_id),
        )
        return con.execute("SELECT * FROM licenses WHERE id=?",(cur.lastrowid,)).fetchone()

def prepare_autotrade_license_pending(telegram_id: int) -> None:
    """Hide the AutoTrade key until the paid customer supplies an MT5 account."""
    with conn() as con:
        con.execute(
            "UPDATE licenses SET license_key=NULL WHERE id=(SELECT id FROM licenses WHERE telegram_id=? AND status='active' AND autotrade_access=1 ORDER BY id DESC LIMIT 1)",
            (int(telegram_id),),
        )


def issue_autotrade_license_for_account(telegram_id: int, account_number: str, broker: str | None = None, server: str | None = None):
    account_number = str(account_number or "").strip()
    if not account_number:
        raise ValueError("MT5 account is required")
    lic = active_license(int(telegram_id))
    if not lic or not bool(lic["autotrade_access"]):
        raise ValueError("no active AutoTrade entitlement")
    key = str(lic["license_key"] or "").strip()
    if key:
        raise ValueError("AutoTrade license has already been issued")
    current = mt5_account(int(telegram_id))
    if current and str(current["account_number"]) != account_number:
        raise ValueError("a different MT5 account is already linked; use the account-change request flow")
    if not current:
        bind_mt5_account(int(telegram_id), account_number, broker, server, None)
    license_key = _new_license_key()
    with conn() as con:
        con.execute("UPDATE licenses SET license_key=? WHERE id=?", (license_key, int(lic["id"])))
        return con.execute("SELECT * FROM licenses WHERE id=?", (int(lic["id"]),)).fetchone()


def admin_extend_license(telegram_id: int, days: int, admin_id: int | None = None, plan_code: str | None = None):
    plan = get_plan(plan_code) if plan_code else None
    return create_or_extend_license(
        telegram_id, None, days, plan_code=plan_code, source="admin", granted_by=admin_id,
        vip_access=(bool(plan["vip_access"]) if plan else True),
        autotrade_access=(bool(plan["autotrade_access"]) if plan else True),
    )


def has_entitlement(telegram_id: int, entitlement: str) -> bool:
    lic=active_license(telegram_id)
    if not lic: return False
    now=datetime.now(timezone.utc)
    if entitlement.lower()=="vip":
        raw=lic["vip_expires_at"] if "vip_expires_at" in lic.keys() else lic["expires_at"]
    elif entitlement.lower()=="autotrade":
        raw=lic["autotrade_expires_at"] if "autotrade_expires_at" in lic.keys() else lic["expires_at"]
    else:
        raise ValueError("unknown entitlement")
    if not raw: return False
    try: return datetime.fromisoformat(str(raw))>now
    except Exception: return False

def license_history(telegram_id: int, limit: int = 30):
    with conn() as con:
        return list(con.execute(
            "SELECT * FROM licenses WHERE telegram_id=? ORDER BY id DESC LIMIT ?",
            (telegram_id, limit),
        ).fetchall())


def expire_license(license_id: int) -> None:
    with conn() as con:
        con.execute("UPDATE licenses SET status='expired' WHERE id=?", (license_id,))


def cancel_active_license(telegram_id: int) -> None:
    with conn() as con:
        con.execute("UPDATE licenses SET status='cancelled' WHERE telegram_id=? AND status='active'", (telegram_id,))
        con.execute("UPDATE subscriptions SET status='cancelled',updated_at=? WHERE user_id=? AND status='active'", (now_iso(),telegram_id))


def list_expired_active():
    with conn() as con:
        return list(con.execute("SELECT * FROM licenses WHERE status='active' AND expires_at<=?", (now_iso(),)).fetchall())


def list_active_licenses():
    with conn() as con:
        return list(con.execute("SELECT * FROM licenses WHERE status='active'").fetchall())


def expiring_count(days: int) -> int:
    end = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    with conn() as con:
        return int(con.execute("SELECT COUNT(*) FROM licenses WHERE status='active' AND expires_at>? AND expires_at<=?", (now_iso(), end)).fetchone()[0])


def entitlement_counts() -> dict[str, int]:
    now=now_iso()
    with conn() as con:
        row=con.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN status='active' AND vip_expires_at>? THEN 1 ELSE 0 END),0) AS vip,
                 COALESCE(SUM(CASE WHEN status='active' AND autotrade_expires_at>? THEN 1 ELSE 0 END),0) AS autotrade
               FROM licenses""",(now,now)).fetchone()
        return {"vip":int(row["vip"] or 0),"autotrade":int(row["autotrade"] or 0)}

def reminder_sent(license_id: int, days_before: int) -> bool:
    with conn() as con:
        return con.execute("SELECT 1 FROM reminders WHERE license_id=? AND days_before=?", (license_id, days_before)).fetchone() is not None


def mark_reminder_sent(license_id: int, days_before: int) -> None:
    with conn() as con:
        con.execute("INSERT OR IGNORE INTO reminders(license_id,days_before,sent_at) VALUES(?,?,?)", (license_id, days_before, now_iso()))


def save_invite(telegram_id: int, license_id: int, invite_link: str) -> None:
    with conn() as con:
        con.execute("INSERT INTO invite_links(telegram_id,license_id,invite_link,created_at) VALUES(?,?,?,?)", (telegram_id, license_id, invite_link, now_iso()))


def get_invite(invite_link: str):
    with conn() as con:
        return con.execute("SELECT * FROM invite_links WHERE invite_link=?", (invite_link,)).fetchone()


def mark_invite_used(invite_link: str) -> None:
    with conn() as con:
        con.execute("UPDATE invite_links SET status='used', used_at=? WHERE invite_link=? AND status='active'", (now_iso(), invite_link))


def active_invites_for_user(telegram_id: int):
    with conn() as con:
        return list(con.execute("SELECT * FROM invite_links WHERE telegram_id=? AND status='active'", (telegram_id,)).fetchall())


def mark_invite_revoked(invite_link: str) -> None:
    with conn() as con:
        con.execute("UPDATE invite_links SET status='revoked', revoked_at=? WHERE invite_link=?", (now_iso(), invite_link))


def get_setting(key: str, default: str = "", con: sqlite3.Connection | None = None) -> str:
    if con is not None:
        row = con.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return str(row[0]) if row else default
    with conn_ctx() as c:
        row = c.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return str(row[0]) if row else default


# Alias avoids name collision with optional `con` argument above.
@contextmanager
def conn_ctx():
    with conn() as c:
        yield c


def set_setting(key: str, value: str) -> None:
    with conn() as con:
        con.execute(
            "INSERT INTO app_settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, str(value), now_iso()),
        )


def points_discount_info(telegram_id: int) -> dict[str, int]:
    user = get_user(telegram_id)
    points = int(user["points_balance"] if user else 0)
    per_pct = max(1, int(get_setting("points_per_percent", "100")))
    max_pct = max(0, min(100, int(get_setting("max_points_discount_percent", "30"))))
    possible_pct = min(max_pct, points // per_pct)
    points_needed = possible_pct * per_pct
    return {"points": points, "points_per_percent": per_pct, "max_percent": max_pct, "possible_percent": possible_pct, "points_needed": points_needed}


def spend_points(telegram_id: int, points: int, reason: str, ref_id: str | None = None) -> bool:
    if points <= 0:
        return True
    with conn() as con:
        row = con.execute("SELECT points_balance FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        if not row or int(row[0]) < points:
            return False
        con.execute("UPDATE users SET points_balance=points_balance-?, updated_at=? WHERE telegram_id=?", (points, now_iso(), telegram_id))
        con.execute("INSERT INTO point_ledger(telegram_id,delta,reason,ref_id,created_at) VALUES(?,?,?,?,?)", (telegram_id, -points, reason, ref_id, now_iso()))
        return True


def refund_points(telegram_id: int, points: int, reason: str, ref_id: str | None = None) -> None:
    if points <= 0:
        return
    with conn() as con:
        con.execute("UPDATE users SET points_balance=points_balance+?, updated_at=? WHERE telegram_id=?", (points, now_iso(), telegram_id))
        con.execute("INSERT INTO point_ledger(telegram_id,delta,reason,ref_id,created_at) VALUES(?,?,?,?,?)", (telegram_id, points, reason, ref_id, now_iso()))


def create_discount(code: str, percent: float, expires_days: int, max_uses: int | None, created_by: int, title_fa: str = "تخفیف NEXUS", title_en: str = "NEXUS Discount") -> int:
    code = code.strip().upper()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=max(1, expires_days))
    with conn() as con:
        cur = con.execute(
            "INSERT INTO discounts(code,title_fa,title_en,percent,max_uses,starts_at,expires_at,active,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (code, title_fa, title_en, float(percent), max_uses, now.isoformat(), exp.isoformat(), 1, created_by, now.isoformat()),
        )
        return int(cur.lastrowid)


def list_discounts(limit: int = 30):
    with conn() as con:
        return list(con.execute("SELECT * FROM discounts ORDER BY id DESC LIMIT ?", (limit,)).fetchall())


def get_valid_discount(code: str, telegram_id: int):
    now = now_iso()
    with conn() as con:
        row = con.execute(
            """
            SELECT * FROM discounts WHERE UPPER(code)=UPPER(?) AND active=1
              AND (starts_at IS NULL OR starts_at<=?)
              AND (expires_at IS NULL OR expires_at>?)
              AND (max_uses IS NULL OR used_count<max_uses)
            """,
            (code.strip(), now, now),
        ).fetchone()
        if not row:
            return None
        used = con.execute("SELECT 1 FROM discount_uses WHERE discount_id=? AND telegram_id=?", (row["id"], telegram_id)).fetchone()
        return None if used else row


def record_discount_use(discount_id: int, telegram_id: int, payment_id: int) -> None:
    with conn() as con:
        con.execute("INSERT OR IGNORE INTO discount_uses(discount_id,telegram_id,payment_id,created_at) VALUES(?,?,?,?)", (discount_id, telegram_id, payment_id, now_iso()))
        con.execute("UPDATE discounts SET used_count=(SELECT COUNT(*) FROM discount_uses WHERE discount_id=?) WHERE id=?", (discount_id, discount_id))


def disable_discount(discount_id: int) -> None:
    with conn() as con:
        con.execute("UPDATE discounts SET active=0 WHERE id=?", (discount_id,))


def save_admin_receipt(payment_id: int, admin_id: int, message_id: int) -> None:
    with conn() as con:
        con.execute("INSERT OR REPLACE INTO admin_receipts(payment_id,admin_id,message_id,created_at) VALUES(?,?,?,?)", (payment_id, admin_id, message_id, now_iso()))


def list_admin_receipts(payment_id: int):
    with conn() as con:
        return list(con.execute("SELECT * FROM admin_receipts WHERE payment_id=?", (payment_id,)).fetchall())


def clear_admin_receipts(payment_id: int) -> None:
    with conn() as con:
        con.execute("DELETE FROM admin_receipts WHERE payment_id=?", (payment_id,))


def stats() -> dict[str, int]:
    with conn() as con:
        return {
            "users": con.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "pending": con.execute("SELECT COUNT(*) FROM payments WHERE status='pending'").fetchone()[0],
            "approved": con.execute("SELECT COUNT(*) FROM payments WHERE status='approved'").fetchone()[0],
            "active": con.execute("SELECT COUNT(*) FROM licenses WHERE status='active' AND expires_at>?", (now_iso(),)).fetchone()[0],
            "expired": con.execute("SELECT COUNT(*) FROM licenses WHERE status IN ('expired','cancelled') OR expires_at<=?", (now_iso(),)).fetchone()[0],
            "referrals": con.execute("SELECT COUNT(*) FROM referral_events WHERE status='rewarded'").fetchone()[0],
            "points": con.execute("SELECT COALESCE(SUM(points_balance),0) FROM users").fetchone()[0],
            "discounts": con.execute("SELECT COUNT(*) FROM discounts WHERE active=1").fetchone()[0],
        }


def add_points(telegram_id: int, points: int, reason: str = "admin_adjustment", ref_id: str | None = None) -> None:
    if points == 0:
        return
    with conn() as con:
        con.execute("UPDATE users SET points_balance=MAX(0, points_balance+?), updated_at=? WHERE telegram_id=?", (points, now_iso(), telegram_id))
        con.execute("INSERT INTO point_ledger(telegram_id,delta,reason,ref_id,created_at) VALUES(?,?,?,?,?)", (telegram_id, points, reason, ref_id, now_iso()))


def get_discount_by_code(code: str):
    with conn() as con:
        return con.execute("SELECT * FROM discounts WHERE UPPER(code)=UPPER(?)", (code.strip(),)).fetchone()


def reserve_discount_use(discount_id: int, telegram_id: int, payment_id: int) -> bool:
    try:
        with conn() as con:
            d = con.execute("SELECT * FROM discounts WHERE id=?", (discount_id,)).fetchone()
            if not d:
                return False
            if d["max_uses"] is not None and int(d["used_count"]) >= int(d["max_uses"]):
                return False
            con.execute("INSERT INTO discount_uses(discount_id,telegram_id,payment_id,created_at) VALUES(?,?,?,?)", (discount_id, telegram_id, payment_id, now_iso()))
            con.execute("UPDATE discounts SET used_count=used_count+1 WHERE id=?", (discount_id,))
            return True
    except sqlite3.IntegrityError:
        return False


def release_discount_use(payment_id: int) -> None:
    with conn() as con:
        rows = list(con.execute("SELECT discount_id FROM discount_uses WHERE payment_id=?", (payment_id,)).fetchall())
        con.execute("DELETE FROM discount_uses WHERE payment_id=?", (payment_id,))
        for r in rows:
            con.execute("UPDATE discounts SET used_count=MAX(0, used_count-1) WHERE id=?", (r["discount_id"],))


def set_discount_active(discount_id: int, active: bool) -> None:
    with conn() as con:
        con.execute("UPDATE discounts SET active=? WHERE id=?", (1 if active else 0, discount_id))


def txid_exists(txid: str) -> bool:
    value = (txid or "").strip().lower()
    if not value:
        return False
    with conn() as con:
        return con.execute("SELECT 1 FROM payments WHERE LOWER(txid)=? LIMIT 1", (value,)).fetchone() is not None


def referral_leaderboard(limit: int = 10, monthly: bool = False):
    with conn() as con:
        if monthly:
            start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
            return list(con.execute(
                """SELECT u.telegram_id,u.username,u.first_name,COUNT(r.id) AS referrals,SUM(r.points) AS points
                   FROM referral_events r JOIN users u ON u.telegram_id=r.referrer_id
                   WHERE r.status='rewarded' AND r.created_at>=?
                   GROUP BY r.referrer_id ORDER BY referrals DESC, points DESC LIMIT ?""", (start, limit)
            ).fetchall())
        return list(con.execute(
            """SELECT u.telegram_id,u.username,u.first_name,COUNT(r.id) AS referrals,SUM(r.points) AS points
               FROM referral_events r JOIN users u ON u.telegram_id=r.referrer_id
               WHERE r.status='rewarded'
               GROUP BY r.referrer_id ORDER BY referrals DESC, points DESC LIMIT ?""", (limit,)
        ).fetchall())


def create_campaign(title_fa: str, title_en: str, percent: float, days: int, plan_code: str | None, audience: str, max_uses: int | None, created_by: int) -> int:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=days)
    with conn() as con:
        cur = con.execute(
            "INSERT INTO campaigns(title_fa,title_en,percent,plan_code,audience,starts_at,expires_at,max_uses,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (title_fa, title_en, percent, plan_code, audience, now.isoformat(), exp.isoformat(), max_uses, created_by, now.isoformat())
        )
        return int(cur.lastrowid)


def list_campaigns(limit: int = 30):
    with conn() as con:
        return list(con.execute("SELECT * FROM campaigns ORDER BY id DESC LIMIT ?", (limit,)).fetchall())


def set_campaign_active(campaign_id: int, active: bool) -> None:
    with conn() as con:
        con.execute("UPDATE campaigns SET active=? WHERE id=?", (1 if active else 0, campaign_id))


def _audience_ok(con: sqlite3.Connection, telegram_id: int, audience: str) -> bool:
    now = now_iso()
    active = con.execute("SELECT 1 FROM licenses WHERE telegram_id=? AND status='active' AND expires_at>? LIMIT 1", (telegram_id, now)).fetchone() is not None
    if audience == 'vip':
        return active
    if audience == 'nonvip':
        return not active
    if audience == 'expired':
        return con.execute("SELECT 1 FROM licenses WHERE telegram_id=? AND expires_at<=? LIMIT 1", (telegram_id, now)).fetchone() is not None and not active
    return True


def best_campaign(telegram_id: int, plan_code: str):
    now = now_iso()
    with conn() as con:
        rows = con.execute(
            """SELECT * FROM campaigns WHERE active=1
               AND (starts_at IS NULL OR starts_at<=?)
               AND (expires_at IS NULL OR expires_at>?)
               AND (plan_code IS NULL OR plan_code='' OR plan_code=?)
               ORDER BY percent DESC, id DESC""", (now, now, plan_code)
        ).fetchall()
        for r in rows:
            if r['max_uses'] is not None and int(r['used_count']) >= int(r['max_uses']):
                continue
            if con.execute("SELECT 1 FROM campaign_uses WHERE campaign_id=? AND telegram_id=?", (r['id'], telegram_id)).fetchone():
                continue
            if _audience_ok(con, telegram_id, r['audience']):
                return r
    return None


def reserve_campaign_use(campaign_id: int, telegram_id: int, payment_id: int) -> bool:
    try:
        with conn() as con:
            r = con.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
            if not r or not r['active']:
                return False
            if r['max_uses'] is not None and int(r['used_count']) >= int(r['max_uses']):
                return False
            con.execute("INSERT INTO campaign_uses(campaign_id,telegram_id,payment_id,created_at) VALUES(?,?,?,?)", (campaign_id,telegram_id,payment_id,now_iso()))
            con.execute("UPDATE campaigns SET used_count=used_count+1 WHERE id=?", (campaign_id,))
            return True
    except sqlite3.IntegrityError:
        return False


def release_campaign_use(payment_id: int) -> None:
    with conn() as con:
        rows=list(con.execute("SELECT campaign_id FROM campaign_uses WHERE payment_id=?",(payment_id,)).fetchall())
        con.execute("DELETE FROM campaign_uses WHERE payment_id=?",(payment_id,))
        for r in rows:
            con.execute("UPDATE campaigns SET used_count=MAX(0,used_count-1) WHERE id=?",(r['campaign_id'],))


def broadcast_targets(target: str, high_points_min: int = 500):
    with conn() as con:
        now=now_iso()
        if target=='vip':
            q="SELECT DISTINCT u.telegram_id FROM users u JOIN licenses l ON l.telegram_id=u.telegram_id WHERE l.status='active' AND l.expires_at>?"; args=(now,)
        elif target=='nonvip':
            q="SELECT u.telegram_id FROM users u WHERE NOT EXISTS(SELECT 1 FROM licenses l WHERE l.telegram_id=u.telegram_id AND l.status='active' AND l.expires_at>?)"; args=(now,)
        elif target=='expired':
            q="SELECT DISTINCT u.telegram_id FROM users u JOIN licenses l ON l.telegram_id=u.telegram_id WHERE l.expires_at<=? AND NOT EXISTS(SELECT 1 FROM licenses a WHERE a.telegram_id=u.telegram_id AND a.status='active' AND a.expires_at>?)"; args=(now,now)
        elif target=='highpoints':
            q="SELECT telegram_id FROM users WHERE points_balance>=?"; args=(high_points_min,)
        else:
            q="SELECT telegram_id FROM users"; args=()
        return [int(r[0]) for r in con.execute(q,args).fetchall()]


def create_broadcast(admin_id: int, target: str, message_text: str, total_count: int) -> int:
    with conn() as con:
        cur=con.execute("INSERT INTO broadcasts(admin_id,target,message_text,total_count,status,created_at) VALUES(?,?,?,?,?,?)",(admin_id,target,message_text,total_count,'sending',now_iso()))
        return int(cur.lastrowid)


def finish_broadcast(broadcast_id: int, sent: int, failed: int) -> None:
    with conn() as con:
        con.execute("UPDATE broadcasts SET sent_count=?,failed_count=?,status='done',finished_at=? WHERE id=?",(sent,failed,now_iso(),broadcast_id))


def campaign_count() -> int:
    with conn() as con:
        return int(con.execute("SELECT COUNT(*) FROM campaigns WHERE active=1 AND (expires_at IS NULL OR expires_at>?)",(now_iso(),)).fetchone()[0])


# ---- v5 CRM / Retention helpers ----
def add_audit(admin_id: int, action: str, target_id: int | None = None, details: str | None = None) -> None:
    with conn() as con:
        con.execute(
            "INSERT INTO audit_logs(admin_id,action,target_id,details,created_at) VALUES(?,?,?,?,?)",
            (admin_id, action, target_id, details, now_iso()),
        )


def recent_audits(limit: int = 20):
    with conn() as con:
        return con.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def join_autotrade_waitlist(telegram_id: int) -> None:
    with conn() as con:
        con.execute(
            "INSERT INTO auto_trade_waitlist(telegram_id,joined_at,active) VALUES(?,?,1) "
            "ON CONFLICT(telegram_id) DO UPDATE SET active=1, joined_at=excluded.joined_at",
            (telegram_id, now_iso()),
        )


def leave_autotrade_waitlist(telegram_id: int) -> None:
    with conn() as con:
        con.execute("UPDATE auto_trade_waitlist SET active=0 WHERE telegram_id=?", (telegram_id,))


def is_on_autotrade_waitlist(telegram_id: int) -> bool:
    with conn() as con:
        row = con.execute("SELECT active FROM auto_trade_waitlist WHERE telegram_id=?", (telegram_id,)).fetchone()
        return bool(row and row["active"])


def autotrade_waitlist_count() -> int:
    with conn() as con:
        return con.execute("SELECT COUNT(*) FROM auto_trade_waitlist WHERE active=1").fetchone()[0]


def autotrade_waitlist_users(limit: int = 20):
    with conn() as con:
        return con.execute(
            "SELECT u.telegram_id,u.username,u.first_name,w.joined_at FROM auto_trade_waitlist w "
            "JOIN users u ON u.telegram_id=w.telegram_id WHERE w.active=1 ORDER BY w.joined_at DESC LIMIT ?",
            (limit,),
        ).fetchall()


def trial_used(telegram_id: int) -> bool:
    with conn() as con:
        return con.execute("SELECT 1 FROM trials WHERE telegram_id=?", (telegram_id,)).fetchone() is not None


def grant_trial(telegram_id: int, days: int, admin_id: int):
    if trial_used(telegram_id):
        return None
    with conn() as con:
        con.execute(
            "INSERT INTO trials(telegram_id,days,granted_by,granted_at) VALUES(?,?,?,?)",
            (telegram_id, days, admin_id, now_iso()),
        )
    # Trial is intentionally VIP-only; Auto Trade remains a paid/admin-granted entitlement.
    return create_or_extend_license(telegram_id, None, days, source="trial", granted_by=admin_id, vip_access=True, autotrade_access=False)


def user_level(telegram_id: int) -> dict[str, object]:
    purchases = count_user_payments(telegram_id)
    refs = referral_stats(telegram_id)["successful"]
    score = purchases * 3 + refs
    if score >= 30:
        return {"key":"diamond","fa":"💎 Diamond","en":"💎 Diamond","score":score}
    if score >= 15:
        return {"key":"gold","fa":"🥇 Gold","en":"🥇 Gold","score":score}
    if score >= 6:
        return {"key":"silver","fa":"🥈 Silver","en":"🥈 Silver","score":score}
    return {"key":"bronze","fa":"🥉 Bronze","en":"🥉 Bronze","score":score}

def user_level_counts() -> dict[str, int]:
    """Compute all user-level buckets in one SQL query (avoids N+1 queries)."""
    with conn() as con:
        row = con.execute(
            """
            WITH payment_counts AS (
                SELECT telegram_id, COUNT(*) AS n
                FROM payments
                WHERE status='approved'
                GROUP BY telegram_id
            ), referral_counts AS (
                SELECT referrer_id AS telegram_id, COUNT(*) AS n
                FROM referral_events
                WHERE status='rewarded'
                GROUP BY referrer_id
            ), scores AS (
                SELECT u.telegram_id, COALESCE(p.n,0)*3 + COALESCE(r.n,0) AS score
                FROM users u
                LEFT JOIN payment_counts p ON p.telegram_id=u.telegram_id
                LEFT JOIN referral_counts r ON r.telegram_id=u.telegram_id
            )
            SELECT
                COALESCE(SUM(CASE WHEN score < 6 THEN 1 ELSE 0 END),0) AS bronze,
                COALESCE(SUM(CASE WHEN score >= 6 AND score < 15 THEN 1 ELSE 0 END),0) AS silver,
                COALESCE(SUM(CASE WHEN score >= 15 AND score < 30 THEN 1 ELSE 0 END),0) AS gold,
                COALESCE(SUM(CASE WHEN score >= 30 THEN 1 ELSE 0 END),0) AS diamond
            FROM scores
            """
        ).fetchone()
        return {k: int(row[k] or 0) for k in ("bronze", "silver", "gold", "diamond")}


def dashboard_stats() -> dict[str, object]:
    today = datetime.now(timezone.utc).date().isoformat()
    month = datetime.now(timezone.utc).strftime('%Y-%m')
    with conn() as con:
        base = stats()
        revenue_today = con.execute(
            "SELECT COALESCE(SUM(amount_usdt),0) FROM payments WHERE status='approved' AND substr(COALESCE(reviewed_at,created_at),1,10)=?", (today,)
        ).fetchone()[0] or 0
        revenue_month = con.execute(
            "SELECT COALESCE(SUM(amount_usdt),0) FROM payments WHERE status='approved' AND substr(COALESCE(reviewed_at,created_at),1,7)=?", (month,)
        ).fetchone()[0] or 0
        revenue_all = con.execute(
            "SELECT COALESCE(SUM(amount_usdt),0) FROM payments WHERE status='approved'"
        ).fetchone()[0] or 0
        trials = con.execute("SELECT COUNT(*) FROM trials").fetchone()[0]
        waitlist = con.execute("SELECT COUNT(*) FROM auto_trade_waitlist WHERE active=1").fetchone()[0]
        return {**base, "revenue_today_usdt":float(revenue_today), "revenue_month_usdt":float(revenue_month), "revenue_all_usdt":float(revenue_all), "trials":trials, "waitlist":waitlist}


# ---- Dynamic subscription plans v6.4 ----
def ensure_default_plans(defaults: dict[str, dict[str, object]]) -> None:
    """Seed the canonical v7.1 commercial catalog once; later admin edits are preserved."""
    now = now_iso()
    with conn() as con:
        migrated = get_setting("pricing_catalog_vnext_migrated", "0", con=con)
        for idx, (code, plan) in enumerate(defaults.items(), start=1):
            con.execute(
                """INSERT OR IGNORE INTO subscription_plans
                   (code,days,title_fa,title_en,irr_price,usdt_price,vip_access,autotrade_access,active,sort_order,created_at,updated_at,service_type,duration_days,price_usdt,setup_fee_usdt,setup_fee_discount_percent,is_active)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(code), int(plan["days"]), str(plan["fa"]), str(plan["en"]), "", str(plan.get("usdt", "0")),
                 1 if bool(plan.get("vip_access", True)) else 0, 1 if bool(plan.get("autotrade_access", True)) else 0,
                 1 if bool(plan.get("active", True)) else 0, idx * 10, now, now, str(plan.get("service_type","signal")), int(plan["days"]),
                 str(plan.get("usdt","0")), str(plan.get("setup_fee_usdt","0")), float(plan.get("setup_fee_discount_percent",0)), 1 if bool(plan.get("active",True)) else 0),
            )
            con.execute(
                """INSERT OR IGNORE INTO plans(code,name,service_type,duration_days,price_usdt,setup_fee_usdt,setup_fee_discount_percent,is_active,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (str(code), str(plan["en"]), str(plan.get("service_type","signal")), int(plan["days"]), str(plan.get("usdt","0")),
                 str(plan.get("setup_fee_usdt","0")), float(plan.get("setup_fee_discount_percent",0)), 1 if bool(plan.get("active",True)) else 0, now, now),
            )
        if migrated != "1":
            legacy_codes = [
                "30","90","180","VIP30","VIP90","VIP180","AUTO30","AUTO90","AUTO180"
            ]
            if legacy_codes:
                con.executemany("UPDATE subscription_plans SET active=0,is_active=0,updated_at=? WHERE code=?", [(now,c) for c in legacy_codes])
            for idx, (code, plan) in enumerate(defaults.items(), start=1):
                con.execute(
                    """UPDATE subscription_plans SET days=?,title_fa=?,title_en=?,irr_price='',usdt_price=?,vip_access=?,autotrade_access=?,active=1,sort_order=?,service_type=?,duration_days=?,price_usdt=?,setup_fee_usdt=?,setup_fee_discount_percent=?,is_active=1,updated_at=? WHERE code=?""",
                    (int(plan["days"]),str(plan["fa"]),str(plan["en"]),str(plan["usdt"]),1 if plan.get("vip_access") else 0,1 if plan.get("autotrade_access") else 0,idx*10,str(plan.get("service_type","signal")),int(plan["days"]),str(plan["usdt"]),str(plan.get("setup_fee_usdt","0")),float(plan.get("setup_fee_discount_percent",0)),now,str(code)),
                )
                con.execute(
                    """UPDATE plans SET name=?,service_type=?,duration_days=?,price_usdt=?,setup_fee_usdt=?,setup_fee_discount_percent=?,is_active=1,updated_at=? WHERE code=?""",
                    (str(plan["en"]),str(plan.get("service_type","signal")),int(plan["days"]),str(plan["usdt"]),str(plan.get("setup_fee_usdt","0")),float(plan.get("setup_fee_discount_percent",0)),now,str(code)),
                )
            con.execute("INSERT INTO app_settings(key,value,updated_at) VALUES('pricing_catalog_vnext_migrated','1',?) ON CONFLICT(key) DO UPDATE SET value='1',updated_at=excluded.updated_at", (now,))
        # Targeted v0.5.8 pricing repair: keep the public title and canonical
        # invoice price identical, and never leave active AutoTrade plans with
        # the placeholder SET_PRICE value. This migration is idempotent.
        catalog_fix = {"VIP12M": "239", "AEX1M": "5", "AEX3M": "14", "AEX6M": "27", "AEX12M": "49"}
        for code, price in catalog_fix.items():
            con.execute("UPDATE subscription_plans SET usdt_price=?, price_usdt=?, updated_at=? WHERE code=?", (price, price, now, code))
            con.execute("UPDATE plans SET price_usdt=?, updated_at=? WHERE code=?", (price, now, code))


def list_plans(*, active_only: bool = False):
    with conn() as con:
        q = "SELECT * FROM subscription_plans"
        args: tuple = ()
        if active_only:
            q += " WHERE active=1"
        q += " ORDER BY sort_order, days, code"
        return list(con.execute(q, args).fetchall())


def get_plan(code: str, *, active_only: bool = False):
    with conn() as con:
        q = "SELECT sp.*, p.id AS canonical_plan_id, p.service_type AS canonical_service_type, p.duration_days AS canonical_duration_days, p.price_usdt AS canonical_price_usdt, p.setup_fee_usdt AS canonical_setup_fee_usdt, p.setup_fee_discount_percent AS canonical_setup_fee_discount_percent FROM subscription_plans sp LEFT JOIN plans p ON p.code=sp.code WHERE sp.code=?"
        args: list[object] = [str(code)]
        if active_only:
            q += " AND sp.active=1"
        return con.execute(q, tuple(args)).fetchone()


def plan_map(*, active_only: bool = True) -> dict[str, dict[str, object]]:
    return {
        str(r["code"]): {
            "days": int(r["duration_days"] or r["days"]),
            "duration_days": int(r["duration_days"] or r["days"]),
            "fa": str(r["title_fa"]),
            "en": str(r["title_en"]),
            "irr": "",
            "usdt": str(r["price_usdt"] if "price_usdt" in r.keys() and r["price_usdt"] is not None else r["usdt_price"]),
            "price_usdt": str(r["price_usdt"] if "price_usdt" in r.keys() and r["price_usdt"] is not None else r["usdt_price"]),
            "setup_fee_usdt": str(r["setup_fee_usdt"] or 0) if "setup_fee_usdt" in r.keys() else "0",
            "setup_fee_discount_percent": float(r["setup_fee_discount_percent"] or 0) if "setup_fee_discount_percent" in r.keys() else 0.0,
            "service_type": str(r["service_type"] or ("auto_trade" if r["autotrade_access"] else "signal")) if "service_type" in r.keys() else ("auto_trade" if r["autotrade_access"] else "signal"),
            "vip_access": bool(r["vip_access"]) if "vip_access" in r.keys() else True,
            "autotrade_access": bool(r["autotrade_access"]) if "autotrade_access" in r.keys() else True,
            "renewal_discount_percent": float(r["renewal_discount_percent"] or 0) if "renewal_discount_percent" in r.keys() else 0.0,
            "upgrade_rank": int(r["upgrade_rank"] or 10) if "upgrade_rank" in r.keys() else 10,
            "active": bool(r["active"]),
        }
        for r in list_plans(active_only=active_only)
    }


def create_plan(
    code: str, days: int, title_fa: str, title_en: str, irr_price: str = "", usdt_price: str = "0",
    *, vip_access: bool = True, autotrade_access: bool = True, renewal_discount_percent: float = 0.0, upgrade_rank: int = 10,
    service_type: str | None = None, setup_fee_usdt: str = "0", setup_fee_discount_percent: float = 0.0,
) -> None:
    code = str(code).strip().upper()
    if not code:
        raise ValueError("plan code is required")
    now = now_iso()
    with conn() as con:
        sort_order = int(con.execute("SELECT COALESCE(MAX(sort_order),0)+10 FROM subscription_plans").fetchone()[0])
        con.execute(
            """INSERT INTO subscription_plans(
                   code,days,title_fa,title_en,irr_price,usdt_price,vip_access,autotrade_access,
                   renewal_discount_percent,upgrade_rank,active,sort_order,created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?,?)""",
            (code, int(days), title_fa.strip(), title_en.strip(), irr_price.strip(), usdt_price.strip() or "SET_PRICE",
             1 if vip_access else 0, 1 if autotrade_access else 0, float(renewal_discount_percent), int(upgrade_rank),
             sort_order, now, now),
        )
        st = service_type or ("auto_trade" if autotrade_access else "signal")
        con.execute("UPDATE subscription_plans SET service_type=?,duration_days=?,price_usdt=?,setup_fee_usdt=?,setup_fee_discount_percent=?,is_active=1 WHERE code=?",
                    (st,int(days),str(usdt_price),str(setup_fee_usdt),float(setup_fee_discount_percent),code))
        con.execute("INSERT OR IGNORE INTO plans(code,name,service_type,duration_days,price_usdt,setup_fee_usdt,setup_fee_discount_percent,is_active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (code,title_en.strip(),st,int(days),str(usdt_price),str(setup_fee_usdt),float(setup_fee_discount_percent),1,now,now))


def update_plan_price(code: str, field: str, value: str) -> None:
    column = {"irr": "irr_price", "usdt": "usdt_price"}.get(field)
    if not column:
        raise ValueError("invalid plan price field")
    with conn() as con:
        now = now_iso()
        con.execute(f"UPDATE subscription_plans SET {column}=?,updated_at=? WHERE code=?", (value.strip(), now, str(code)))
        if field == "usdt":
            con.execute("UPDATE subscription_plans SET price_usdt=? WHERE code=?", (value.strip(), str(code)))
            con.execute("UPDATE plans SET price_usdt=?,updated_at=? WHERE code=?", (value.strip(), now, str(code)))


def update_plan_setup_fee(code: str, amount_usdt: str, discount_percent: float | None = None) -> None:
    amount = str(amount_usdt).strip()
    pct = None if discount_percent is None else max(0.0, min(100.0, float(discount_percent)))
    with conn() as con:
        now = now_iso()
        if pct is None:
            con.execute("UPDATE subscription_plans SET setup_fee_usdt=?,updated_at=? WHERE code=?", (amount,now,str(code)))
            con.execute("UPDATE plans SET setup_fee_usdt=?,updated_at=? WHERE code=?", (amount,now,str(code)))
        else:
            con.execute("UPDATE subscription_plans SET setup_fee_usdt=?,setup_fee_discount_percent=?,updated_at=? WHERE code=?", (amount,pct,now,str(code)))
            con.execute("UPDATE plans SET setup_fee_usdt=?,setup_fee_discount_percent=?,updated_at=? WHERE code=?", (amount,pct,now,str(code)))


def set_plan_active(code: str, active: bool) -> None:
    with conn() as con:
        now = now_iso()
        flag = 1 if active else 0
        con.execute("UPDATE subscription_plans SET active=?,is_active=?,updated_at=? WHERE code=?", (flag,flag,now,str(code)))
        con.execute("UPDATE plans SET is_active=?,updated_at=? WHERE code=?", (flag,now,str(code)))


def update_plan_entitlement(code: str, entitlement: str, enabled: bool) -> None:
    column = {"vip": "vip_access", "auto": "autotrade_access", "autotrade": "autotrade_access"}.get(entitlement.lower())
    if not column:
        raise ValueError("invalid entitlement")
    with conn() as con:
        con.execute(f"UPDATE subscription_plans SET {column}=?,updated_at=? WHERE code=?", (1 if enabled else 0, now_iso(), str(code)))


def update_plan_renewal_discount(code: str, percent: float) -> None:
    percent = float(percent)
    if not 0 <= percent <= 100:
        raise ValueError("invalid renewal discount")
    with conn() as con:
        con.execute("UPDATE subscription_plans SET renewal_discount_percent=?,updated_at=? WHERE code=?", (percent, now_iso(), str(code)))


def update_plan_upgrade_rank(code: str, rank: int) -> None:
    with conn() as con:
        con.execute("UPDATE subscription_plans SET upgrade_rank=?,updated_at=? WHERE code=?", (int(rank), now_iso(), str(code)))


# ---- Signal Engine v6.4 ----
def create_signal(*, market_type: str, symbol: str, direction: str, entry_price: float, stop_loss: float,
                  targets: list[float], risk_percent: float, rr_ratio: float | None,
                  destination: str, chart_file_id: str | None, created_by: int,
                  lot_size: float | None = None, leverage: float | None = None,
                  trailing_code: str | None = None, trailing_name: str | None = None,
                  trailing_config: dict | None = None, max_entry_deviation_pct: float | None = None,
                  max_entry_deviation_abs: float | None = None, order_type: str = "MARKET",
                  volume_mode: str = "RISK", publish_token: str | None = None, timeframe: str = "M5",
                  stop_limit_price: float | None = None):
    if publish_token:
        with conn() as con:
            existing=con.execute("SELECT * FROM signals WHERE publish_token=?",(str(publish_token),)).fetchone()
            if existing:
                return existing
    market = str(market_type or "").strip().upper()
    direction = str(direction or "").strip().upper()
    destination = str(destination or "").strip().upper()
    order_type = str(order_type or "MARKET").strip().upper()
    volume_mode = str(volume_mode or "RISK").strip().upper()
    timeframe = str(timeframe or "M5").strip().upper()
    if timeframe not in {"M1","M3","M5","M15","M30","H1","H4","D1","W1"}:
        raise ValueError("invalid timeframe")
    if market not in {"FOREX", "CRYPTO", "GOLD", "INDEX", "OTHER"}:
        raise ValueError("invalid market type")
    if direction not in {"BUY", "SELL", "LONG", "SHORT"}:
        raise ValueError("invalid direction")
    if destination not in {"FREE", "VIP", "BOTH"}:
        raise ValueError("invalid destination")
    if order_type not in {"MARKET", "LIMIT", "BUY_LIMIT", "SELL_LIMIT", "BUY_STOP", "SELL_STOP", "BUY_STOP_LIMIT", "SELL_STOP_LIMIT"}:
        raise ValueError("invalid order type")
    if volume_mode not in {"RISK", "FIXED"}:
        raise ValueError("invalid volume mode")
    entry = float(entry_price)
    stop = float(stop_loss)
    slimit = None if stop_limit_price is None else float(stop_limit_price)
    if slimit is not None and (not math.isfinite(slimit) or slimit <= 0):
        raise ValueError("stop-limit price must be positive and finite")
    if order_type in {"BUY_STOP_LIMIT","SELL_STOP_LIMIT"} and slimit is None:
        raise ValueError("stop-limit price is required for STOP_LIMIT orders")
    if order_type == "BUY_STOP_LIMIT" and slimit is not None and slimit < entry:
        raise ValueError("BUY_STOP_LIMIT stop-limit price must be at or above stop price")
    if order_type == "SELL_STOP_LIMIT" and slimit is not None and slimit > entry:
        raise ValueError("SELL_STOP_LIMIT stop-limit price must be at or below stop price")
    if order_type in {"BUY_LIMIT","BUY_STOP","BUY_STOP_LIMIT"} and direction not in {"BUY","LONG"}:
        raise ValueError("BUY pending order requires BUY/LONG direction")
    if order_type in {"SELL_LIMIT","SELL_STOP","SELL_STOP_LIMIT"} and direction not in {"SELL","SHORT"}:
        raise ValueError("SELL pending order requires SELL/SHORT direction")
    if not all(map(lambda x: math.isfinite(x), (entry, stop, float(risk_percent)))):
        raise ValueError("non-finite signal value")
    if entry <= 0 or stop <= 0:
        raise ValueError("entry and stop-loss must be positive")
    if not 0 <= float(risk_percent) <= 100:
        raise ValueError("risk percent must be between 0 and 100")

    clean_targets = [float(v) for v in targets]
    if not clean_targets:
        raise ValueError("at least one take-profit target is required")
    if len(clean_targets) > 30:
        raise ValueError("too many take-profit targets")
    if any((not math.isfinite(v) or v <= 0) for v in clean_targets):
        raise ValueError("take-profit targets must be finite and positive")
    is_long = direction in {"BUY", "LONG"}
    if is_long and stop >= entry:
        raise ValueError("LONG stop-loss must be below entry")
    if not is_long and stop <= entry:
        raise ValueError("SHORT stop-loss must be above entry")
    if is_long and any(v <= entry for v in clean_targets):
        raise ValueError("LONG take-profit targets must be above entry")
    if not is_long and any(v >= entry for v in clean_targets):
        raise ValueError("SHORT take-profit targets must be below entry")
    if any(clean_targets[i] >= clean_targets[i+1] for i in range(len(clean_targets)-1)) if is_long else any(clean_targets[i] <= clean_targets[i+1] for i in range(len(clean_targets)-1)):
        raise ValueError("take-profit targets must be strictly ordered")
    # Keep the original tp1/tp2/tp3 columns populated for backward-compatible reports.
    tp1 = clean_targets[0]
    tp2 = clean_targets[1] if len(clean_targets) > 1 else None
    tp3 = clean_targets[2] if len(clean_targets) > 2 else None
    if trailing_config is None and trailing_code:
        try:
            from .autotrade.trailing_profiles import profile_snapshot
            trailing_config = profile_snapshot(trailing_code)
        except Exception:
            trailing_config = None
    trailing_config_json = json.dumps(trailing_config, ensure_ascii=False, separators=(",", ":")) if trailing_config else None
    with conn() as con:
        try:
            cur = con.execute(
                """INSERT INTO signals(publish_token,market_type,symbol,timeframe,direction,entry_price,stop_loss,tp1,tp2,tp3,risk_percent,rr_ratio,
                                          destination,chart_file_id,volume_mode,lot_size,leverage,trailing_code,trailing_name,trailing_config_json,max_entry_deviation_pct,max_entry_deviation_abs,order_type,stop_limit_price,status,created_by,created_at,cycle_id)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'DRAFT', ?, ?, ?)""",
                (publish_token,market, symbol.strip().upper(), timeframe, direction, entry, stop, tp1, tp2, tp3,
                 risk_percent, rr_ratio, destination, chart_file_id, volume_mode, lot_size, leverage, trailing_code, trailing_name,
                 trailing_config_json, max_entry_deviation_pct, max_entry_deviation_abs, order_type, slimit, created_by, now_iso(), get_setting("current_cycle_id", "CYCLE-LEGACY", con=con)),
            )
        except sqlite3.IntegrityError:
            if publish_token:
                existing=con.execute("SELECT * FROM signals WHERE publish_token=?", (str(publish_token),)).fetchone()
                if existing:
                    return existing
            raise
        signal_id = int(cur.lastrowid)
        code = f"NX-{signal_id:04d}"
        con.execute("UPDATE signals SET code=? WHERE id=?", (code, signal_id))
        con.executemany(
            "INSERT INTO signal_targets(signal_id,target_no,price) VALUES(?,?,?)",
            [(signal_id, idx, price) for idx, price in enumerate(clean_targets, 1)],
        )
        return con.execute("SELECT * FROM signals WHERE id=?", (signal_id,)).fetchone()


def get_signal_targets(signal_id: int):
    with conn() as con:
        return list(con.execute(
            "SELECT target_no,price FROM signal_targets WHERE signal_id=? ORDER BY target_no",
            (signal_id,),
        ).fetchall())


def _ensure_signal_authority_columns(row):
    return row


def add_signal_event(signal_id: int, event_type: str, *, actor_type: str, actor_id: str | int | None = None,
                     account_number: str | None = None, revision: int | None = None, result: str = "SUCCESS",
                     reason: str | None = None, payload: dict | None = None, request_id: str | None = None,
                     correlation_id: str | None = None) -> int:
    signal = get_signal(signal_id)
    if not signal:
        raise ValueError("signal not found")
    now = now_iso()
    rev = int(revision if revision is not None else (signal["revision"] or 1))
    suuid = str(signal["signal_uuid"] or "") if "signal_uuid" in signal.keys() else ""
    with conn() as con:
        cur = con.execute(
            """INSERT INTO signal_events_v060
               (signal_id,signal_uuid,revision,event_type,actor_type,actor_id,account_number,event_time,request_id,correlation_id,result,reason,payload_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (int(signal_id), suuid or None, rev, str(event_type).upper(), str(actor_type).upper(),
             None if actor_id is None else str(actor_id), None if account_number is None else str(account_number),
             now, request_id, correlation_id, str(result).upper(), reason,
             json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":"))),
        )
        return int(cur.lastrowid)


def issue_mt5_admin_signal(*, market_type: str, symbol: str, direction: str, entry_price: float, stop_loss: float,
                           targets: list[float], risk_percent: float, rr_ratio: float | None, order_type: str,
                           volume_mode: str = "RISK", lot_size: float | None = None, leverage: float | None = None,
                           trailing_code: str | None = None, trailing_name: str | None = None, trailing_config: dict | None = None,
                           max_entry_deviation_pct: float | None = None, max_entry_deviation_abs: float | None = None,
                           timeframe: str = "M5", stop_limit_price: float | None = None,
                           admin_account: str, admin_id: int, request_id: str | None = None,
                           signal_code: str | None = None, destination: str = "BOTH") -> sqlite3.Row:
    # Canonical issuer path for v0.6.0. Telegram publication is handled by the
    # API layer after the durable signal row is committed.
    token = str(signal_code or "").strip() or ("MT5ADMIN-" + secrets.token_urlsafe(18))
    existing = get_signal_by_publish_token(token)
    if existing:
        return existing
    suuid = str(__import__('uuid').uuid4())
    destination = str(destination or "BOTH").strip().upper()
    if destination not in {"FREE", "VIP", "BOTH"}:
        raise ValueError("invalid destination")
    row = create_signal(
        market_type=market_type, symbol=symbol, direction=direction, entry_price=entry_price,
        stop_loss=stop_loss, targets=targets, risk_percent=risk_percent, rr_ratio=rr_ratio,
        destination=destination, chart_file_id=None, created_by=int(admin_id), lot_size=lot_size, leverage=leverage,
        trailing_code=trailing_code, trailing_name=trailing_name, trailing_config=trailing_config,
        max_entry_deviation_pct=max_entry_deviation_pct, max_entry_deviation_abs=max_entry_deviation_abs,
        order_type=order_type, volume_mode=volume_mode, publish_token=token, timeframe=timeframe,
        stop_limit_price=stop_limit_price,
    )
    now = now_iso()
    with conn() as con:
        con.execute(
            "UPDATE signals SET signal_uuid=?,revision=1,issuer_type='MT5_ADMIN',issuer_account=?,issued_at=?,status='ACTIVE' WHERE id=?",
            (suuid, str(admin_account), now, int(row["id"])),
        )
        row = con.execute("SELECT * FROM signals WHERE id=?", (int(row["id"]),)).fetchone()
    add_signal_event(int(row["id"]), "ISSUE", actor_type="MT5_ADMIN", actor_id=admin_id, account_number=admin_account,
                     revision=1, request_id=request_id, correlation_id=str(row["code"]),
                     payload={"order_type": str(row["order_type"]), "symbol": str(row["symbol"]), "direction": str(row["direction"]),
                              "entry": float(row["entry_price"]), "sl": float(row["stop_loss"])})
    return row


def record_signal_delivery(signal_id: int, account_number: str, *, status: str = "RECEIVED", ticket: str | None = None, error_text: str | None = None):
    signal = get_signal(signal_id)
    if not signal:
        raise ValueError("signal not found")
    now = now_iso()
    with conn() as con:
        con.execute(
            """INSERT INTO signal_deliveries_v060(signal_id,signal_uuid,account_number,first_seen_at,processed_at,status,ticket,error_text)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(signal_id,account_number) DO UPDATE SET
                 processed_at=excluded.processed_at,status=excluded.status,ticket=COALESCE(excluded.ticket,signal_deliveries_v060.ticket),error_text=excluded.error_text""",
            (int(signal_id), str(signal["signal_uuid"] or ""), str(account_number), now,
             now if str(status).upper() not in {"RECEIVED","SEEN"} else None, str(status).upper(), ticket, error_text),
        )


def record_mt5_heartbeat(account_number: str, *, role: str = "CLIENT", ea_version: str | None = None, payload: dict | None = None):
    with conn() as con:
        con.execute(
            """INSERT INTO mt5_heartbeats_v060(account_number,role,ea_version,last_seen_at,payload_json) VALUES(?,?,?,?,?)
               ON CONFLICT(account_number) DO UPDATE SET role=excluded.role,ea_version=excluded.ea_version,last_seen_at=excluded.last_seen_at,payload_json=excluded.payload_json""",
            (str(account_number), str(role).upper(), ea_version, now_iso(), json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":"))),
        )


def upsert_mt5_live_snapshot(account_number: str, *, broker: str = "", server: str = "", ea_version: str = "", positions: list[dict] | None = None, orders: list[dict] | None = None) -> dict:
    """Replace the account's authoritative live MT5 snapshot atomically.

    The snapshot is the source of truth for the Telegram Admin Live Center.
    Missing rows are marked CLOSED/CANCELLED by type, so stale signals cannot
    remain visible merely because their signal row is still ACTIVE.
    """
    account = str(account_number).strip()
    if not account:
        raise ValueError("account number is required")
    now = now_iso()
    positions = positions or []
    orders = orders or []
    with conn() as con:
        seen_pos=[]; seen_ord=[]
        for item in positions[:200]:
            ident=str(item.get("identifier") or item.get("ticket") or "").strip()
            ticket=str(item.get("ticket") or "").strip()
            if not ident or not ticket or not str(item.get("symbol") or "").strip():
                continue
            seen_pos.append(ident)
            con.execute("""INSERT INTO mt5_live_state
                (account_number,state_type,identifier,ticket,signal_code,symbol,direction,volume,entry_price,current_price,stop_loss,take_profit,profit,magic,nexus_managed,order_type,status,broker,server,last_seen_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(account_number,state_type,identifier) DO UPDATE SET
                 ticket=excluded.ticket,signal_code=excluded.signal_code,symbol=excluded.symbol,direction=excluded.direction,volume=excluded.volume,
                 entry_price=excluded.entry_price,current_price=excluded.current_price,stop_loss=excluded.stop_loss,take_profit=excluded.take_profit,profit=excluded.profit,
                 magic=excluded.magic,nexus_managed=excluded.nexus_managed,order_type=excluded.order_type,status='OPEN',broker=excluded.broker,server=excluded.server,last_seen_at=excluded.last_seen_at""",
                (account,"POSITION",ident,ticket,str(item.get("signal_code") or "").strip(),str(item.get("symbol") or "").upper(),str(item.get("direction") or "").upper(),
                 float(item.get("volume") or 0),float(item.get("entry_price") or 0),float(item.get("current_price") or 0),float(item.get("stop_loss") or 0),float(item.get("take_profit") or 0),float(item.get("profit") or 0),
                 int(item.get("magic") or 0),1 if item.get("nexus_managed") else 0,str(item.get("order_type") or "MARKET").upper(),"OPEN",broker,server,now))
        for item in orders[:200]:
            ident=str(item.get("identifier") or item.get("ticket") or "").strip(); ticket=str(item.get("ticket") or "").strip()
            if not ident or not ticket or not str(item.get("symbol") or "").strip(): continue
            seen_ord.append(ident)
            con.execute("""INSERT INTO mt5_live_state
                (account_number,state_type,identifier,ticket,signal_code,symbol,direction,volume,entry_price,current_price,stop_loss,take_profit,profit,magic,nexus_managed,order_type,status,broker,server,last_seen_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(account_number,state_type,identifier) DO UPDATE SET
                 ticket=excluded.ticket,signal_code=excluded.signal_code,symbol=excluded.symbol,direction=excluded.direction,volume=excluded.volume,entry_price=excluded.entry_price,current_price=excluded.current_price,
                 stop_loss=excluded.stop_loss,take_profit=excluded.take_profit,profit=excluded.profit,magic=excluded.magic,nexus_managed=excluded.nexus_managed,order_type=excluded.order_type,
                 status='PENDING',broker=excluded.broker,server=excluded.server,last_seen_at=excluded.last_seen_at""",
                (account,"ORDER",ident,ticket,str(item.get("signal_code") or "").strip(),str(item.get("symbol") or "").upper(),str(item.get("direction") or "").upper(),
                 float(item.get("volume") or 0),float(item.get("entry_price") or 0),float(item.get("current_price") or 0),float(item.get("stop_loss") or 0),float(item.get("take_profit") or 0),0.0,
                 int(item.get("magic") or 0),1 if item.get("nexus_managed") else 0,str(item.get("order_type") or "").upper(),"PENDING",broker,server,now))
        # Snapshot is authoritative: anything absent is no longer live.
        if seen_pos:
            con.execute("UPDATE mt5_live_state SET status='CLOSED' WHERE account_number=? AND state_type='POSITION' AND status='OPEN' AND identifier NOT IN (%s)" % ','.join('?'*len(seen_pos)), (account,*seen_pos))
        else:
            con.execute("UPDATE mt5_live_state SET status='CLOSED' WHERE account_number=? AND state_type='POSITION' AND status='OPEN'", (account,))
        if seen_ord:
            con.execute("UPDATE mt5_live_state SET status='CANCELLED' WHERE account_number=? AND state_type='ORDER' AND status='PENDING' AND identifier NOT IN (%s)" % ','.join('?'*len(seen_ord)), (account,*seen_ord))
        else:
            con.execute("UPDATE mt5_live_state SET status='CANCELLED' WHERE account_number=? AND state_type='ORDER' AND status='PENDING'", (account,))
        con.execute("UPDATE mt5_heartbeats_v060 SET last_seen_at=?,ea_version=COALESCE(?,ea_version) WHERE account_number=?", (now,ea_version or None,account))
    return {"account_number":account,"positions":len(seen_pos),"orders":len(seen_ord),"last_seen_at":now}


def mt5_live_positions(account_number: str, *, nexus_only: bool = True) -> list[dict]:
    with conn() as con:
        q="SELECT * FROM mt5_live_state WHERE account_number=? AND state_type='POSITION' AND status='OPEN'"
        args=[str(account_number)]
        if nexus_only:
            q += " AND nexus_managed=1"
        q += " ORDER BY id" if False else " ORDER BY last_seen_at DESC, ticket DESC"
        return [dict(r) for r in con.execute(q,args).fetchall()]

def mt5_live_for_signal(signal_code: str, account_number: str | None = None) -> list[dict]:
    with conn() as con:
        if account_number:
            rows=con.execute("SELECT * FROM mt5_live_state WHERE account_number=? AND signal_code=? AND status IN ('OPEN','PENDING') ORDER BY state_type,last_seen_at DESC",(str(account_number),str(signal_code))).fetchall()
        else:
            rows=con.execute("SELECT * FROM mt5_live_state WHERE signal_code=? AND status IN ('OPEN','PENDING') ORDER BY last_seen_at DESC",(str(signal_code),)).fetchall()
        return [dict(r) for r in rows]


def mt5_live_orders(account_number: str, *, nexus_only: bool = True) -> list[dict]:
    with conn() as con:
        q="SELECT * FROM mt5_live_state WHERE account_number=? AND state_type='ORDER' AND status='PENDING'"; args=[str(account_number)]
        if nexus_only: q += " AND nexus_managed=1"
        q += " ORDER BY last_seen_at DESC, ticket DESC"
        return [dict(r) for r in con.execute(q,args).fetchall()]

def mt5_live_accounts() -> list[dict]:
    with conn() as con:
        rows=con.execute("SELECT account_number,role,ea_version,last_seen_at,payload_json FROM mt5_heartbeats_v060 ORDER BY last_seen_at DESC").fetchall()
        return [dict(r) for r in rows]


def mt5_signal_live_state(signal_id: int) -> dict:
    """Return the authoritative MT5 receipt + latest execution snapshot for the signal issuer."""
    signal = get_signal(signal_id)
    if not signal:
        return {}
    uid = int(signal["created_by"])
    with conn() as con:
        receipt = con.execute(
            "SELECT status,ticket,error_text,first_seen_at,executed_at FROM autotrade_signal_receipts "
            "WHERE signal_id=? AND telegram_id=? AND platform='MT5'", (int(signal_id), uid)
        ).fetchone()
        trade = con.execute(
            "SELECT * FROM autotrade_trade_executions WHERE signal_id=? AND telegram_id=? "
            "ORDER BY id DESC LIMIT 1", (int(signal_id), uid)
        ).fetchone()
    result = {"receipt_status": str(receipt["status"]).upper() if receipt else "NOT_RECEIVED",
              "ticket": str(receipt["ticket"] or "") if receipt else "",
              "receipt_error": str(receipt["error_text"] or "") if receipt else "",
              "trade_status": str(trade["status"]).upper() if trade else "NO_TRADE",
              "trade": dict(trade) if trade else None}
    return result


def list_mt5_publication_retries(limit: int = 50):
    """Return broker-accepted MT5 signals that still lack a requested channel post.

    Telegram delivery is a durable retry concern, not a one-shot BackgroundTask.
    Only EXECUTED/PENDING/ACTIVATED receipts for the MT5 authority qualify.
    """
    with conn() as con:
        rows = con.execute(
            """SELECT s.*, r.status AS receipt_status
               FROM signals s
               JOIN autotrade_signal_receipts r
                 ON r.signal_id=s.id AND r.telegram_id=s.created_by AND r.platform='MT5'
              WHERE s.issuer_type='MT5_ADMIN'
                AND s.status NOT IN ('REJECTED','CANCELLED','EXPIRED','PUBLISH_FAILED')
                AND LOWER(r.status) IN ('executed','pending','activated')
                AND ((s.destination IN ('FREE','BOTH') AND s.free_message_id IS NULL)
                  OR (s.destination IN ('VIP','BOTH') AND s.vip_message_id IS NULL))
              ORDER BY s.id ASC LIMIT ?""",
            (max(1, min(int(limit), 200)),),
        ).fetchall()
        return list(rows)


def list_mt5_admin_signals(limit: int = 50):
    with conn() as con:
        return list(con.execute("SELECT * FROM signals WHERE issuer_type='MT5_ADMIN' ORDER BY id DESC LIMIT ?", (max(1,min(int(limit),200)),)).fetchall())

def list_mt5_active_signals(limit: int = 20):
    with conn() as con:
        return list(con.execute(
            "SELECT * FROM signals WHERE issuer_type='MT5_ADMIN' AND status NOT IN ('CLOSED','REJECTED','CANCELLED','EXPIRED') ORDER BY id DESC LIMIT ?",
            (max(1, min(int(limit), 200)),),
        ).fetchall())


def list_mt5_closed_signals(limit: int = 20):
    with conn() as con:
        return list(con.execute(
            "SELECT * FROM signals WHERE issuer_type='MT5_ADMIN' AND status='CLOSED' ORDER BY id DESC LIMIT ?",
            (max(1, min(int(limit), 200)),),
        ).fetchall())


def mt5_signal_stats() -> dict[str, float | int]:
    with conn() as con:
        total = int(con.execute("SELECT COUNT(*) FROM signals WHERE issuer_type='MT5_ADMIN' AND status='CLOSED'").fetchone()[0])
        wins = int(con.execute("SELECT COUNT(*) FROM signals WHERE issuer_type='MT5_ADMIN' AND status='CLOSED' AND result_value>0").fetchone()[0])
        losses = int(con.execute("SELECT COUNT(*) FROM signals WHERE issuer_type='MT5_ADMIN' AND status='CLOSED' AND result_value<0").fetchone()[0])
        be = int(con.execute("SELECT COUNT(*) FROM signals WHERE issuer_type='MT5_ADMIN' AND status='CLOSED' AND ABS(COALESCE(result_value,0))<0.0000001").fetchone()[0])
        active = int(con.execute("SELECT COUNT(*) FROM signals WHERE issuer_type='MT5_ADMIN' AND status NOT IN ('CLOSED','REJECTED','CANCELLED','EXPIRED')").fetchone()[0])
        return {"total": total, "wins": wins, "losses": losses, "be": be, "active": active,
                "win_rate": round((wins / total * 100) if total else 0, 1)}


def get_signal(signal_id: int):
    with conn() as con:
        return con.execute("SELECT * FROM signals WHERE id=?", (signal_id,)).fetchone()



def get_signal_by_publish_token(publish_token: str):
    with conn() as con:
        return con.execute("SELECT * FROM signals WHERE publish_token=?", (str(publish_token),)).fetchone()

def get_signal_by_code(code: str):
    with conn() as con:
        return con.execute("SELECT * FROM signals WHERE UPPER(code)=UPPER(?)", (code.strip(),)).fetchone()


def list_active_signals(limit: int = 20):
    with conn() as con:
        return list(con.execute("SELECT * FROM signals WHERE status<>'CLOSED' ORDER BY id DESC LIMIT ?", (limit,)).fetchall())


def list_closed_signals(limit: int = 20):
    with conn() as con:
        return list(con.execute("SELECT * FROM signals WHERE status='CLOSED' ORDER BY id DESC LIMIT ?", (limit,)).fetchall())


def claim_signal_channel(signal_id: int, channel: str) -> bool:
    """Atomically claim publication of one signal/channel."""
    channel = str(channel).upper().strip()
    if channel not in {"FREE", "VIP"}:
        raise ValueError("invalid channel")
    try:
        with conn() as con:
            con.execute(
                "INSERT INTO autotrade_publish_claims(signal_id,channel,claimed_at) VALUES(?,?,?)",
                (int(signal_id), channel, now_iso()),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def release_signal_channel_claim(signal_id: int, channel: str) -> None:
    channel = str(channel).upper().strip()
    with conn() as con:
        con.execute(
            "DELETE FROM autotrade_publish_claims WHERE signal_id=? AND channel=?",
            (int(signal_id), channel),
        )


def save_mt5_signal_publication_asset(signal_id: int, file_path: str) -> None:
    with conn() as con:
        con.execute(
            "INSERT INTO mt5_signal_publication_assets(signal_id,file_path,created_at) VALUES(?,?,?) "
            "ON CONFLICT(signal_id) DO UPDATE SET file_path=excluded.file_path,created_at=excluded.created_at",
            (int(signal_id), str(file_path), now_iso()),
        )

def get_mt5_signal_publication_asset(signal_id: int) -> str | None:
    with conn() as con:
        row=con.execute("SELECT file_path FROM mt5_signal_publication_assets WHERE signal_id=?", (int(signal_id),)).fetchone()
        return str(row[0]) if row and row[0] else None

def clear_mt5_signal_publication_asset(signal_id: int) -> None:
    path = get_mt5_signal_publication_asset(signal_id)
    with conn() as con:
        con.execute("DELETE FROM mt5_signal_publication_assets WHERE signal_id=?", (int(signal_id),))
    if path:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass


def set_signal_publish_messages(signal_id: int, free_message_id: int | None, vip_message_id: int | None) -> None:
    """Merge newly-published channel messages without erasing existing reply chains."""
    with conn() as con:
        if free_message_id is not None:
            con.execute(
                "UPDATE signals SET free_message_id=COALESCE(free_message_id,?),free_last_message_id=? WHERE id=?",
                (free_message_id, free_message_id, signal_id),
            )
        if vip_message_id is not None:
            con.execute(
                "UPDATE signals SET vip_message_id=COALESCE(vip_message_id,?),vip_last_message_id=? WHERE id=?",
                (vip_message_id, vip_message_id, signal_id),
            )


def set_signal_latest_reply(
    signal_id: int, *, free_message_id: int | None = None,
    vip_message_id: int | None = None
) -> None:
    """Atomically advance the channel-specific Reply Chain tail."""
    sets=[]; args=[]
    if free_message_id is not None:
        sets.append("free_last_message_id=?"); args.append(int(free_message_id))
    if vip_message_id is not None:
        sets.append("vip_last_message_id=?"); args.append(int(vip_message_id))
    if not sets:
        return
    args.append(int(signal_id))
    with conn() as con:
        con.execute(f"UPDATE signals SET {', '.join(sets)} WHERE id=?", tuple(args))

def set_signal_status(signal_id: int, status: str) -> None:
    with conn() as con:
        con.execute("UPDATE signals SET status=? WHERE id=?", (status, signal_id))


def mark_limit_activated(signal_id: int) -> None:
    with conn() as con:
        con.execute("UPDATE signals SET limit_activated_at=COALESCE(limit_activated_at,?),status='ACTIVE' WHERE id=?", (now_iso(), signal_id))


def add_signal_update(signal_id: int, action: str, detail_fa: str, detail_en: str, value: str | None,
                      admin_id: int, free_message_id: int | None = None, vip_message_id: int | None = None,
                      status: str | None = None) -> None:
    with conn() as con:
        con.execute(
            "INSERT INTO signal_updates(signal_id,action,detail_fa,detail_en,value,free_message_id,vip_message_id,admin_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (signal_id, action, detail_fa, detail_en, value, free_message_id, vip_message_id, admin_id, now_iso()),
        )
        sets=[]; args=[]
        if free_message_id is not None:
            sets.append("free_last_message_id=?"); args.append(free_message_id)
        if vip_message_id is not None:
            sets.append("vip_last_message_id=?"); args.append(vip_message_id)
        if status:
            sets.append("status=?"); args.append(status)
        if action == 'PARTIAL' and value is not None:
            try:
                sets.append("partial_percent=?"); args.append(float(value))
            except ValueError:
                pass
        if action == 'TRAILING':
            sets.append("trailing_value=?"); args.append(value)
        command_map = {
            "BREAK_EVEN": "MOVE_SL_TO_ENTRY",
            "PARTIAL": "PARTIAL_CLOSE",
            "TRAILING": "ACTIVATE_TRAILING",
            "TP_UPDATE": "UPDATE_TP",
            "SL_UPDATE": "UPDATE_SL",
            "CLOSE": "CLOSE_SIGNAL",
        }
        command = command_map.get(str(action).upper())
        if command:
            payload = None
            if value is not None:
                payload = json.dumps({"value": value}, ensure_ascii=False, separators=(",", ":"))
            con.execute(
                "INSERT INTO autotrade_commands(signal_id,command,payload_json,created_at) VALUES(?,?,?,?)",
                (signal_id, command, payload, now_iso()),
            )
        if sets:
            args.append(signal_id)
            con.execute(f"UPDATE signals SET {', '.join(sets)} WHERE id=?", tuple(args))



def get_signal_by_autotrade_signal_id(telegram_id: int, signal_id: str):
    with conn() as con:
        return con.execute(
            """SELECT s.* FROM signals s
               WHERE s.created_by=? AND s.publish_token=?
               ORDER BY s.id DESC LIMIT 1""",
            (int(telegram_id), str(signal_id).strip()),
        ).fetchone()

def get_signal_by_autotrade_ticket(telegram_id: int, ticket: str):
    with conn() as con:
        return con.execute(
            """SELECT s.* FROM signals s
               JOIN autotrade_signal_receipts r ON r.signal_id=s.id
               WHERE r.telegram_id=? AND r.platform='MT5' AND r.ticket=?
               ORDER BY s.id DESC LIMIT 1""",
            (int(telegram_id), str(ticket)),
        ).fetchone()

def bind_mt5_account(telegram_id: int, account_number: str, broker: str | None, server: str | None, ea_version: str | None = None):
    account_number = str(account_number).strip()
    if not account_number:
        raise ValueError("account number is required")
    now = now_iso()
    with conn() as con:
        existing = con.execute("SELECT * FROM autotrade_mt5_accounts WHERE telegram_id=?", (telegram_id,)).fetchone()
        if existing and str(existing["account_number"]) != account_number:
            raise ValueError("license already linked to another MT5 account")
        owner = con.execute("SELECT telegram_id FROM autotrade_mt5_accounts WHERE account_number=?", (account_number,)).fetchone()
        if owner and int(owner["telegram_id"]) != int(telegram_id):
            raise ValueError("MT5 account is already linked to another user")
        con.execute(
            """INSERT INTO autotrade_mt5_accounts(telegram_id,account_number,broker,server,status,ea_version,bound_at,last_seen_at)
               VALUES(?,?,?,?, 'active', ?, ?, ?)
               ON CONFLICT(telegram_id) DO UPDATE SET
                 broker=excluded.broker,server=excluded.server,status='active',ea_version=excluded.ea_version,last_seen_at=excluded.last_seen_at""",
            (telegram_id, account_number, broker, server, ea_version, now, now),
        )
        return con.execute("SELECT * FROM autotrade_mt5_accounts WHERE telegram_id=?", (telegram_id,)).fetchone()


def mt5_account(telegram_id: int):
    with conn() as con:
        return con.execute("SELECT * FROM autotrade_mt5_accounts WHERE telegram_id=?", (telegram_id,)).fetchone()


def request_mt5_account_change(telegram_id: int, new_account_number: str, broker: str | None = None,
                                 server: str | None = None, reason: str | None = None):
    new_account_number = str(new_account_number or "").strip()
    if not new_account_number:
        raise ValueError("new MT5 account is required")
    current = mt5_account(int(telegram_id))
    if not current:
        raise ValueError("no active MT5 account is linked")
    if str(current["account_number"]) == new_account_number:
        raise ValueError("new MT5 account is the current account")
    with conn() as con:
        owner = con.execute(
            "SELECT telegram_id FROM autotrade_mt5_accounts WHERE account_number=? AND status='active'",
            (new_account_number,),
        ).fetchone()
        if owner and int(owner["telegram_id"]) != int(telegram_id):
            raise ValueError("MT5 account is already linked to another user")
        existing = con.execute(
            "SELECT id FROM autotrade_account_change_requests WHERE telegram_id=? AND new_account_number=? AND status='PENDING'",
            (int(telegram_id), new_account_number),
        ).fetchone()
        if existing:
            return con.execute("SELECT * FROM autotrade_account_change_requests WHERE id=?", (int(existing["id"]),)).fetchone()
        lic = con.execute("SELECT id FROM licenses WHERE telegram_id=? AND autotrade_access=1 ORDER BY id DESC LIMIT 1", (int(telegram_id),)).fetchone()
        cur = con.execute(
            """INSERT INTO autotrade_account_change_requests
               (telegram_id,license_id,old_account_number,new_account_number,broker,server,status,requested_at,reason)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (int(telegram_id), int(lic["id"]) if lic else None, str(current["account_number"]), new_account_number,
             broker, server, "PENDING", now_iso(), reason),
        )
        return con.execute("SELECT * FROM autotrade_account_change_requests WHERE id=?", (cur.lastrowid,)).fetchone()


def pending_mt5_account_change_requests():
    with conn() as con:
        return list(con.execute(
            "SELECT * FROM autotrade_account_change_requests WHERE status='PENDING' ORDER BY requested_at ASC"
        ).fetchall())


def review_mt5_account_change(request_id: int, admin_id: int, approve: bool, reason: str | None = None):
    with conn() as con:
        req = con.execute("SELECT * FROM autotrade_account_change_requests WHERE id=?", (int(request_id),)).fetchone()
        if not req:
            raise ValueError("account change request not found")
        if str(req["status"]).upper() != "PENDING":
            raise ValueError("account change request is already reviewed")
        if not approve:
            con.execute(
                "UPDATE autotrade_account_change_requests SET status='REJECTED',reviewed_at=?,reviewed_by=?,reason=? WHERE id=?",
                (now_iso(), int(admin_id), reason or "Rejected by admin", int(request_id)),
            )
            return con.execute("SELECT * FROM autotrade_account_change_requests WHERE id=?", (int(request_id),)).fetchone()
        owner = con.execute(
            "SELECT telegram_id FROM autotrade_mt5_accounts WHERE account_number=? AND status='active'",
            (str(req["new_account_number"]),),
        ).fetchone()
        if owner and int(owner["telegram_id"]) != int(req["telegram_id"]):
            raise ValueError("new MT5 account is already linked to another user")
        now = now_iso()
        current = con.execute("SELECT * FROM autotrade_mt5_accounts WHERE telegram_id=?", (int(req["telegram_id"]),)).fetchone()
        if current:
            con.execute(
                """INSERT INTO autotrade_mt5_account_history
                   (telegram_id,account_number,broker,server,status,valid_from,valid_to,change_request_id,changed_by,reason)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (int(req["telegram_id"]), str(current["account_number"]), current["broker"], current["server"],
                 "replaced", str(current["bound_at"]), now, int(request_id), int(admin_id), reason or "Account changed by admin"),
            )
        # Keep the current-account table one-row-per-customer; historical rows
        # live in the append-only history table instead of being overwritten.
        con.execute(
            """UPDATE autotrade_mt5_accounts
               SET account_number=?,broker=?,server=?,status='active',ea_version=NULL,bound_at=?,last_seen_at=?
               WHERE telegram_id=?""",
            (str(req["new_account_number"]), req["broker"], req["server"], now, now, int(req["telegram_id"])),
        )
        con.execute(
            "UPDATE autotrade_account_change_requests SET status='APPROVED',reviewed_at=?,reviewed_by=?,reason=? WHERE id=?",
            (now_iso(), int(admin_id), reason or "Approved by admin", int(request_id)),
        )
        return con.execute("SELECT * FROM autotrade_account_change_requests WHERE id=?", (int(request_id),)).fetchone()

def touch_autotrade_session(telegram_id: int, account_number: str, ea_version: str | None, platform: str = "MT5") -> None:
    now = now_iso()
    with conn() as con:
        con.execute(
            """INSERT INTO autotrade_sessions(telegram_id,platform,account_number,ea_version,last_ping_at,status)
               VALUES(?,?,?,?,?,'online')
               ON CONFLICT(telegram_id,platform) DO UPDATE SET
                 account_number=excluded.account_number,ea_version=excluded.ea_version,last_ping_at=excluded.last_ping_at,status='online'""",
            (telegram_id, platform.upper(), str(account_number), ea_version, now),
        )
        con.execute("UPDATE autotrade_mt5_accounts SET last_seen_at=?,ea_version=COALESCE(?,ea_version) WHERE telegram_id=?", (now, ea_version, telegram_id))


def autotrade_active_signals(after_id: int = 0, limit: int = 50):
    with conn() as con:
        return list(con.execute(
            """SELECT * FROM signals
               WHERE id>? AND status='ACTIVE'
                 AND issuer_type='MT5_ADMIN'
               ORDER BY id ASC LIMIT ?""",
            (int(after_id), max(1, min(int(limit), 100))),
        ).fetchall())


def create_autotrade_command(signal_id: int, command: str, payload: dict | None = None, *, actor_type: str = "MT5_ADMIN", actor_id: str | int | None = None, account_number: str | None = None) -> int:
    signal = get_signal(signal_id)
    if not signal:
        raise ValueError("signal not found")
    if "issuer_type" in signal.keys() and str(signal["issuer_type"]).upper() != "MT5_ADMIN":
        raise ValueError("only MT5_ADMIN signals accept v0.6 admin commands")
    now = now_iso()
    with conn() as con:
        cur = con.execute("INSERT INTO autotrade_commands(signal_id,command,payload_json,created_at) VALUES(?,?,?,?)",
                          (int(signal_id), str(command).upper(), json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":")), now))
        command_id = int(cur.lastrowid)
    add_signal_event(signal_id, "COMMAND", actor_type=actor_type, actor_id=actor_id, account_number=account_number,
                     request_id=f"CMD-{command_id}", correlation_id=str(signal["code"]),
                     payload={"command": str(command).upper(), "command_id": command_id, **(payload or {})})
    return command_id


def autotrade_commands(after_id: int = 0, limit: int = 100):
    with conn() as con:
        return list(con.execute(
            "SELECT * FROM autotrade_commands WHERE id>? ORDER BY id ASC LIMIT ?",
            (int(after_id), max(1, min(int(limit), 200))),
        ).fetchall())


def ensure_admin_identity(telegram_id: int) -> None:
    """Ensure the configured MT5 Admin identity satisfies users foreign keys."""
    upsert_user(int(telegram_id), "NEXUS_ADMIN", "NEXUS Admin")


def mark_signal_receipt(signal_id: int, telegram_id: int, *, status: str, ticket: str | None = None, error_text: str | None = None, platform: str = "MT5", account_number: str | None = None) -> None:
    signal = get_signal(signal_id)
    if not signal:
        raise ValueError("signal not found")
    if str(signal["status"]).upper() in {"PUBLISH_FAILED", "CANCELLED", "CLOSED"}:
        raise ValueError("signal is not eligible for Auto Trade receipt")
    # v0.6 MT5-authority signals intentionally have no Telegram message IDs.
    if str(signal["issuer_type"] if "issuer_type" in signal.keys() else "").upper() != "MT5_ADMIN" and not signal["free_message_id"] and not signal["vip_message_id"]:
        raise ValueError("signal is not eligible for Auto Trade receipt")
    if "issuer_type" in signal.keys() and str(signal["issuer_type"]).upper() == "MT5_ADMIN" and account_number:
        record_signal_delivery(signal_id, str(account_number), status=status, ticket=ticket, error_text=error_text)
    if str(signal["order_type"]).upper() == "LIMIT" and str(status).lower() == "activated" and not signal["limit_activated_at"]:
        pass
    # The receipt is accepted only for the license owner. The API authenticates the license and account first.
    # MT5 Admin is a system identity; provision it idempotently before the FK insert
    # so a fresh DB can never turn a valid broker receipt into HTTP 500.
    try:
        from .config import settings as _settings
        if int(telegram_id) in {int(x) for x in _settings.admin_ids}:
            ensure_admin_identity(int(telegram_id))
    except Exception:
        # Never let optional provisioning logic hide the original receipt path.
        pass
    now = now_iso()
    status_l=str(status).lower()
    executed_at = now if status_l in {"executed","activated","rejected","failed","closed"} else None
    with conn() as con:
        # Receipt state is per-user and must never mutate the global signal lifecycle.
        # A user activation cannot publish or activate a signal for every other license holder.
        con.execute(
            """INSERT INTO autotrade_signal_receipts(signal_id,telegram_id,platform,status,first_seen_at,executed_at,ticket,error_text)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(signal_id,telegram_id,platform) DO UPDATE SET
                 status=excluded.status,executed_at=COALESCE(excluded.executed_at,autotrade_signal_receipts.executed_at),
                 ticket=COALESCE(excluded.ticket,autotrade_signal_receipts.ticket),error_text=excluded.error_text""",
            (signal_id, telegram_id, platform.upper(), status, now, executed_at, ticket, error_text),
        )
        event_key=f"signal:{signal_id}:{telegram_id}:{platform.upper()}:{str(status).lower()}"
        payload=json.dumps({"status":status,"ticket":ticket,"error":error_text},ensure_ascii=False)
        con.execute("INSERT OR IGNORE INTO autotrade_notifications(telegram_id,event_key,event_type,signal_id,payload_json,created_at) VALUES(?,?,?,?,?,?)",
                    (telegram_id,event_key,"SIGNAL_RECEIPT",signal_id,payload,now))

    # MT5_ADMIN is the single execution authority for channel publication.
    # Its receipt may advance the canonical signal state; customer receipts are
    # deliberately per-user and never mutate the global signal lifecycle.
    if str(signal["issuer_type"] if "issuer_type" in signal.keys() else "").upper() == "MT5_ADMIN" and account_number and str(signal["issuer_account"] or "") == str(account_number):
        if status_l in {"executed", "pending"}:
            set_signal_status(signal_id, "ACTIVE")
        elif status_l in {"rejected", "failed"}:
            set_signal_status(signal_id, "REJECTED")


def mark_command_receipt(command_id: int, telegram_id: int, *, status: str, error_text: str | None = None, platform: str = "MT5") -> None:
    with conn() as check_con:
        cmd = check_con.execute("SELECT id,signal_id FROM autotrade_commands WHERE id=?", (command_id,)).fetchone()
    if not cmd:
        raise ValueError("command not found")
    now = now_iso()
    executed_at = now if status.lower() in {"executed","failed","ignored"} else None
    with conn() as con:
        con.execute(
            """INSERT INTO autotrade_command_receipts(command_id,telegram_id,platform,status,received_at,executed_at,error_text)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(command_id,telegram_id,platform) DO UPDATE SET
                 status=excluded.status,executed_at=COALESCE(excluded.executed_at,autotrade_command_receipts.executed_at),error_text=excluded.error_text""",
            (command_id, telegram_id, platform.upper(), status, now, executed_at, error_text),
        )
        event_key=f"command:{command_id}:{telegram_id}:{platform.upper()}:{str(status).lower()}"
        payload=json.dumps({"status":status,"error":error_text},ensure_ascii=False)
        cmd=con.execute("SELECT signal_id,command FROM autotrade_commands WHERE id=?",(command_id,)).fetchone()
        con.execute("INSERT OR IGNORE INTO autotrade_notifications(telegram_id,event_key,event_type,signal_id,command_id,payload_json,created_at) VALUES(?,?,?,?,?,?,?)",
                    (telegram_id,event_key,"COMMAND_RECEIPT",int(cmd["signal_id"]) if cmd else None,command_id,payload,now))



def enqueue_autotrade_trade_event(telegram_id: int, event_name: str, payload: dict, ticket: str) -> None:
    """Queue an MT5 lifecycle event with durable idempotency.

    MT5 may resend the same event after an HTTP timeout.  The event_id is
    therefore part of the durable uniqueness key; UPDATE events are never
    deduplicated merely by ticket+event type.
    """
    event_name = str(event_name).upper().strip()
    ticket = str(ticket).strip()
    # Legacy contract: if event_name not in {"OPEN", "PENDING", "UPDATE", "CLOSE"}:
    # is extended below with CANCEL/EXPIRE for pending lifecycle events.
    if event_name not in {"OPEN", "PENDING", "UPDATE", "CLOSE", "CANCEL", "EXPIRE"}:
        raise ValueError("unsupported MT5 event")
    if not ticket:
        raise ValueError("ticket is required")

    event_id = str(payload.get("event_id") or "").strip()
    if not event_id:
        # Deterministic fallback: retries after an HTTP timeout must not create
        # a second ledger row merely because the retry happened later.
        fingerprint = "|".join(str(payload.get(k, "")) for k in (
            "event", "ticket", "signal_id", "symbol", "direction",
            "volume", "entry_price", "stop_loss", "take_profit",
            "exit_price", "profit", "event_time_ms"
        ))
        event_id = "legacy-" + hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:32]

    payload = dict(payload)
    payload["event_id"] = event_id
    payload["event"] = event_name

    event_key = f"mt5:{int(telegram_id)}:{ticket}:{event_id}"
    now = now_iso()
    with conn() as con:
        con.execute(
            """INSERT OR IGNORE INTO autotrade_notifications
               (telegram_id,event_key,event_type,signal_id,command_id,payload_json,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (
                int(telegram_id), event_key, "MT5_TRADE_EVENT",
                None, None, json.dumps(payload, ensure_ascii=False, separators=(",", ":")), now,
            ),
        )
        # Durable trade ledger. signal_id/cycle_id are resolved later when needed.
        con.execute(
            """INSERT OR IGNORE INTO autotrade_trade_executions
               (telegram_id,signal_id,ticket,event_id,event_type,destination,symbol,direction,volume,
                entry_price,stop_loss,take_profit,exit_price,profit,gross_profit,commission,swap,slippage,risk_cash,realized_r,position_id,deal_id,cycle_id,status,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                int(telegram_id), None, ticket, event_id, event_name,
                str(payload.get("destination") or "BOTH").upper(),
                str(payload.get("symbol") or "").upper(),
                str(payload.get("direction") or "").upper(),
                float(payload.get("volume") or 0),
                float(payload.get("entry_price") or 0),
                float(payload.get("stop_loss") or 0),
                float(payload.get("take_profit") or 0),
                float(payload.get("exit_price") or 0),
                float(payload.get("profit") or 0),
                float(payload.get("gross_profit") or payload.get("profit") or 0),
                float(payload.get("commission") or 0),
                float(payload.get("swap") or 0),
                float(payload.get("slippage") or 0),
                float(payload.get("risk_cash") or 0),
                float(payload.get("realized_r") or 0) if payload.get("realized_r") is not None else None,
                str(payload.get("position_id") or "") or None,
                str(payload.get("deal_id") or ticket) or None,
                str(payload.get("cycle_id") or get_setting("current_cycle_id", "CYCLE-LEGACY", con=con)),
                "QUEUED", now, now,
            ),
        )

def has_trade_execution(telegram_id: int, ticket: str, event_id: str) -> bool:
    with conn() as con:
        return con.execute(
            "SELECT 1 FROM autotrade_trade_executions WHERE telegram_id=? AND ticket=? AND event_id=? LIMIT 1",
            (int(telegram_id), str(ticket), str(event_id)),
        ).fetchone() is not None


def update_trade_execution(
    telegram_id: int, ticket: str, event_id: str, *,
    signal_id: int | None = None, status: str | None = None,
    error_text: str | None = None, destination: str | None = None
) -> None:
    sets = ["updated_at=?"]
    args = [now_iso()]
    if signal_id is not None:
        sets.append("signal_id=?"); args.append(int(signal_id))
    if status is not None:
        sets.append("status=?"); args.append(str(status).upper())
    if error_text is not None:
        sets.append("error_text=?"); args.append(str(error_text)[:2000])
    if destination is not None:
        sets.append("destination=?"); args.append(str(destination).upper())
    args.extend([int(telegram_id), str(ticket), str(event_id)])
    with conn() as con:
        con.execute(
            f"UPDATE autotrade_trade_executions SET {', '.join(sets)} "
            "WHERE telegram_id=? AND ticket=? AND event_id=?",
            tuple(args),
        )

def autotrade_trade_executions(telegram_id: int, *, start_iso: str | None = None,
                                end_iso: str | None = None, limit: int = 500):
    with conn() as con:
        q = """SELECT e.*, s.code, s.status AS signal_status
               FROM autotrade_trade_executions e
               LEFT JOIN signals s ON s.id=e.signal_id
               WHERE e.telegram_id=?"""
        args=[int(telegram_id)]
        if start_iso is not None:
            q += " AND e.created_at>=?"; args.append(start_iso)
        if end_iso is not None:
            q += " AND e.created_at<?"; args.append(end_iso)
        q += " ORDER BY e.created_at ASC, e.id ASC LIMIT ?"
        args.append(max(1,min(int(limit),2000)))
        return list(con.execute(q,tuple(args)).fetchall())

def claim_autotrade_notification(notification_id: int) -> bool:
    with conn() as con:
        cur = con.execute("UPDATE autotrade_notifications SET claimed_at=? WHERE id=? AND sent_at IS NULL AND claimed_at IS NULL", (now_iso(), notification_id))
        return cur.rowcount == 1


def release_autotrade_notification_claim(notification_id: int) -> None:
    with conn() as con:
        con.execute("UPDATE autotrade_notifications SET claimed_at=NULL WHERE id=? AND sent_at IS NULL", (notification_id,))


def pending_autotrade_notifications(limit: int = 100):
    with conn() as con:
        return list(con.execute("SELECT * FROM autotrade_notifications WHERE sent_at IS NULL AND claimed_at IS NULL ORDER BY id LIMIT ?",(max(1,min(int(limit),500)),)).fetchall())


def mark_autotrade_notification_sent(notification_id: int):
    with conn() as con:
        con.execute("UPDATE autotrade_notifications SET sent_at=? WHERE id=?",(now_iso(),notification_id))


def update_signal_sl(signal_id: int, stop_loss: float, *, status: str | None = None) -> None:
    with conn() as con:
        if status:
            con.execute("UPDATE signals SET stop_loss=?,status=? WHERE id=?", (stop_loss, status, signal_id))
        else:
            con.execute("UPDATE signals SET stop_loss=? WHERE id=?", (stop_loss, signal_id))


def update_signal_tp(signal_id: int, target_no: int | str, value: float) -> None:
    if isinstance(target_no, str):
        m = re.fullmatch(r"tp([1-9][0-9]?)", target_no.strip().lower())
        if not m:
            raise ValueError('invalid TP field')
        target_no = int(m.group(1))
    target_no = int(target_no)
    if target_no < 1:
        raise ValueError('invalid TP number')
    with conn() as con:
        exists = con.execute("SELECT 1 FROM signal_targets WHERE signal_id=? AND target_no=?", (signal_id, target_no)).fetchone()
        if not exists:
            raise ValueError('TP target does not exist')
        con.execute("UPDATE signal_targets SET price=? WHERE signal_id=? AND target_no=?", (float(value), signal_id, target_no))
        # Mirror first three targets to legacy columns used by older reports/tools.
        if target_no <= 3:
            con.execute(f"UPDATE signals SET tp{target_no}=? WHERE id=?", (float(value), signal_id))


def mark_signal_opened(signal_id: int, opened_at: str | None = None) -> None:
    with conn() as con:
        con.execute(
            "UPDATE signals SET opened_at=COALESCE(opened_at,?), status='ACTIVE', limit_activated_at=COALESCE(limit_activated_at,?) WHERE id=?",
            (opened_at or now_iso(), opened_at or now_iso(), signal_id),
        )


def close_signal(
    signal_id: int,
    exit_price: float,
    result_value: float,
    result_unit: str,
    result_chart_file_id: str | None,
    closed_at: str | None = None,
    *,
    close_reason: str | None = None,
    holding_seconds: int | None = None,
    result_pips: float | None = None,
) -> None:
    with conn() as con:
        con.execute(
            """UPDATE signals
               SET status='CLOSED',closed_at=?,exit_price=?,result_value=?,result_unit=?,
                   result_chart_file_id=?,close_reason=?,holding_seconds=?,result_pips=?
               WHERE id=?""",
            (closed_at or now_iso(), exit_price, result_value, result_unit, result_chart_file_id,
             close_reason, holding_seconds, result_pips, signal_id),
        )


def reconcile_mt5_history(telegram_id: int, items: list[dict]) -> dict:
    """Reconcile broker-confirmed MT5 history into the durable execution ledger.

    This path is intentionally idempotent and does not publish Telegram messages.
    It repairs missed MT5 lifecycle events and, when a NEXUS signal can be matched,
    repairs the signal's CLOSED state using the broker's realized net P/L.
    """
    accepted = created = matched = repaired = 0
    skipped = 0
    with conn() as con:
        for item in items[:500]:
            event = str(item.get("event") or "").upper().strip()
            if event not in {"OPEN", "CLOSE"}:
                skipped += 1; continue
            ticket = str(item.get("ticket") or "").strip()
            event_id = str(item.get("event_id") or "").strip()
            if not ticket or not event_id:
                skipped += 1; continue
            occurred_at = str(item.get("event_time") or "")
            if not occurred_at:
                try:
                    epoch_ms = int(item.get("event_time_ms") or 0)
                    if epoch_ms > 0:
                        from datetime import datetime, timezone
                        occurred_at = datetime.fromtimestamp(epoch_ms / 1000.0, tz=timezone.utc).isoformat()
                except Exception:
                    occurred_at = ""
            if not occurred_at:
                occurred_at = now_iso()
            signal_token = str(item.get("signal_id") or "").strip()
            signal_row = None
            if signal_token:
                signal_row = con.execute("SELECT * FROM signals WHERE publish_token=?", (signal_token,)).fetchone()
            if not signal_row:
                code = str(item.get("code") or "").strip()
                if code:
                    signal_row = con.execute("SELECT * FROM signals WHERE UPPER(code)=UPPER(?)", (code,)).fetchone()

            existing = con.execute(
                "SELECT * FROM autotrade_trade_executions WHERE telegram_id=? AND ticket=? AND event_id=?",
                (int(telegram_id), ticket, event_id),
            ).fetchone()
            if existing:
                accepted += 1
                if signal_row and existing["signal_id"] is None:
                    con.execute("UPDATE autotrade_trade_executions SET signal_id=?,status='RECONCILED',updated_at=? WHERE id=?",
                                (int(signal_row["id"]), now_iso(), int(existing["id"])))
                continue

            # If an event-driven CLOSE already exists for this signal, don't create
            # a second close row just because reconciliation used a deterministic id.
            if signal_row:
                prior = con.execute(
                    "SELECT * FROM autotrade_trade_executions WHERE telegram_id=? AND signal_id=? AND event_type=? ORDER BY id DESC LIMIT 1",
                    (int(telegram_id), int(signal_row["id"]), event),
                ).fetchone()
                if prior:
                    con.execute("UPDATE autotrade_trade_executions SET status='RECONCILED',updated_at=? WHERE id=?",
                                (now_iso(), int(prior["id"])))
                    accepted += 1
                    if event == "CLOSE" and str(signal_row["status"]).upper() != "CLOSED":
                        exit_price = float(item.get("exit_price") or 0)
                        profit = float(item.get("profit") or 0)
                        if exit_price > 0:
                            con.execute(
                                "UPDATE signals SET status='CLOSED',closed_at=?,exit_price=?,result_value=?,result_unit='USD' WHERE id=?",
                                (occurred_at, exit_price, profit, int(signal_row["id"])),
                            )
                            repaired += 1
                    continue

            con.execute(
                """INSERT INTO autotrade_trade_executions
                   (telegram_id,signal_id,ticket,event_id,event_type,destination,symbol,direction,volume,
                    entry_price,stop_loss,take_profit,exit_price,profit,gross_profit,commission,swap,slippage,risk_cash,realized_r,position_id,deal_id,cycle_id,status,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (int(telegram_id), int(signal_row["id"]) if signal_row else None, ticket, event_id, event,
                 str(item.get("destination") or "BOTH").upper(), str(item.get("symbol") or "").upper(),
                 str(item.get("direction") or "").upper(), float(item.get("volume") or 0),
                 float(item.get("entry_price") or 0), float(item.get("stop_loss") or 0),
                 float(item.get("take_profit") or 0), float(item.get("exit_price") or 0),
                 float(item.get("profit") or 0), float(item.get("gross_profit") or item.get("profit") or 0),
                 float(item.get("commission") or 0), float(item.get("swap") or 0), float(item.get("slippage") or 0),
                 float(item.get("risk_cash") or 0),
                 float(item.get("realized_r") or 0) if item.get("realized_r") is not None else None,
                 str(item.get("position_id") or "") or None, str(item.get("deal_id") or ticket) or None,
                 str(item.get("cycle_id") or get_setting("current_cycle_id", "CYCLE-LEGACY", con=con)),
                 "RECONCILED", occurred_at, now_iso()),
            )
            created += 1; accepted += 1
            if signal_row:
                matched += 1
                if event == "OPEN":
                    # OPEN reconciliation only links the execution ledger; the
                    # signal itself remains ACTIVE until broker-confirmed CLOSE.
                    pass
                elif event == "CLOSE" and str(signal_row["status"]).upper() != "CLOSED":
                    exit_price = float(item.get("exit_price") or 0)
                    if exit_price > 0:
                        con.execute(
                            "UPDATE signals SET status='CLOSED',closed_at=?,exit_price=?,result_value=?,result_unit='USD' WHERE id=?",
                            (occurred_at, exit_price, float(item.get("profit") or 0), int(signal_row["id"])),
                        )
                        repaired += 1
    return {"accepted": accepted, "created": created, "matched": matched, "repaired": repaired, "skipped": skipped}


def signal_updates(signal_id: int):
    with conn() as con:
        return list(con.execute("SELECT * FROM signal_updates WHERE signal_id=? ORDER BY id", (signal_id,)).fetchall())


def current_cycle_id() -> str:
    return str(get_setting("current_cycle_id", "CYCLE-LEGACY")).strip() or "CYCLE-LEGACY"


def start_new_cycle(cycle_id: str | None = None) -> str:
    value = str(cycle_id or "").strip()
    if not value:
        value = "CYCLE-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    with conn() as con:
        con.execute(
            "INSERT INTO app_settings(key,value,updated_at) VALUES('current_cycle_id',?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
            (value, now_iso()),
        )
    return value


def unified_cycle_report(telegram_id: int, cycle_id: str | None = None) -> dict:
    """Return one reconciled report: signal plan + broker execution truth."""
    cycle = str(cycle_id or current_cycle_id())
    with conn() as con:
        rows = con.execute(
            """SELECT e.*, s.code,s.market_type,s.rr_ratio,s.risk_percent,s.entry_price AS planned_entry,
                      s.stop_loss AS planned_sl,s.cycle_id AS signal_cycle
               FROM autotrade_trade_executions e
               LEFT JOIN signals s ON s.id=e.signal_id
               WHERE e.telegram_id=? AND COALESCE(e.cycle_id,s.cycle_id,?)=?
               ORDER BY e.created_at ASC,e.id ASC""",
            (int(telegram_id), cycle, cycle),
        ).fetchall()
    grouped = {}
    for r in rows:
        key = str(r["position_id"] or r["ticket"])
        g = grouped.setdefault(key, {"open": None, "close": None, "updates": []})
        typ = str(r["event_type"]).upper()
        if typ == "OPEN" and g["open"] is None: g["open"] = r
        elif typ == "CLOSE": g["close"] = r
        else: g["updates"].append(r)
    closed=[]
    for key,g in grouped.items():
        c=g["close"]
        if c is None: continue
        o=g["open"] or c
        net=float(c["profit"] or 0)
        risk_cash=float(c["risk_cash"] or (o["risk_cash"] if o else 0) or 0)
        realized_r=(net/risk_cash) if risk_cash>0 else (float(c["realized_r"]) if c["realized_r"] is not None else None)
        closed.append({"ticket":str(c["ticket"]),"position_id":str(c["position_id"] or key),"signal_id":o["code"] if o["code"] else None,
                       "symbol":str(c["symbol"] or o["symbol"] or ""),"direction":str(c["direction"] or o["direction"] or ""),
                       "entry":float(o["entry_price"] or o["planned_entry"] or 0),"exit":float(c["exit_price"] or 0),
                       "net_pnl":net,"gross_pnl":float(c["gross_profit"] or c["profit"] or 0),
                       "commission":float(c["commission"] or 0),"swap":float(c["swap"] or 0),
                       "slippage":float(c["slippage"] or 0),"realized_r":realized_r,
                       "planned_rr":float(o["rr_ratio"]) if o["rr_ratio"] is not None else None})
    wins=sum(1 for x in closed if x["net_pnl"]>0); losses=sum(1 for x in closed if x["net_pnl"]<0); be=len(closed)-wins-losses
    net=sum(x["net_pnl"] for x in closed)
    return {"cycle_id":cycle,"closed":len(closed),"wins":wins,"losses":losses,"be":be,
            "win_rate":round(wins/len(closed)*100,1) if closed else 0.0,"net_pnl":round(net,2),
            "gross_pnl":round(sum(x["gross_pnl"] for x in closed),2),"commission":round(sum(x["commission"] for x in closed),2),
            "swap":round(sum(x["swap"] for x in closed),2),"avg_realized_r":round(sum(x["realized_r"] for x in closed if x["realized_r"] is not None)/max(1,len([x for x in closed if x["realized_r"] is not None])),2),
            "trades":closed}


def signal_stats() -> dict[str, float | int]:
    with conn() as con:
        total = int(con.execute("SELECT COUNT(*) FROM signals WHERE status='CLOSED'").fetchone()[0])
        wins = int(con.execute("SELECT COUNT(*) FROM signals WHERE status='CLOSED' AND result_value>0").fetchone()[0])
        losses = int(con.execute("SELECT COUNT(*) FROM signals WHERE status='CLOSED' AND result_value<0").fetchone()[0])
        be = int(con.execute("SELECT COUNT(*) FROM signals WHERE status='CLOSED' AND ABS(COALESCE(result_value,0))<0.0000001").fetchone()[0])
        active = int(con.execute("SELECT COUNT(*) FROM signals WHERE status<>'CLOSED'").fetchone()[0])
        forex_pips = float(con.execute("SELECT COALESCE(SUM(result_value),0) FROM signals WHERE status='CLOSED' AND market_type='FOREX' AND result_unit='PIPS'").fetchone()[0] or 0)
        crypto_pct = float(con.execute("SELECT COALESCE(SUM(result_value),0) FROM signals WHERE status='CLOSED' AND market_type='CRYPTO' AND result_unit='PERCENT'").fetchone()[0] or 0)
        return {'total':total,'wins':wins,'losses':losses,'be':be,'active':active,'win_rate':round((wins/total*100) if total else 0,1),'forex_pips':round(forex_pips,1),'crypto_pct':round(crypto_pct,2)}


# ---- Automatic trading reports v6.3 ----
def trading_report_stats(start_iso: str, end_iso: str) -> dict:
    """Aggregate one local trading period converted to UTC [start, end)."""
    with conn() as con:
        opened = int(con.execute(
            "SELECT COUNT(*) FROM signals WHERE created_at>=? AND created_at<?", (start_iso, end_iso)
        ).fetchone()[0])
        closed = int(con.execute(
            "SELECT COUNT(*) FROM signals WHERE status='CLOSED' AND closed_at>=? AND closed_at<?", (start_iso, end_iso)
        ).fetchone()[0])
        wins = int(con.execute(
            "SELECT COUNT(*) FROM signals WHERE status='CLOSED' AND closed_at>=? AND closed_at<? AND result_value>0", (start_iso, end_iso)
        ).fetchone()[0])
        losses = int(con.execute(
            "SELECT COUNT(*) FROM signals WHERE status='CLOSED' AND closed_at>=? AND closed_at<? AND result_value<0", (start_iso, end_iso)
        ).fetchone()[0])
        be = int(con.execute(
            "SELECT COUNT(*) FROM signals WHERE status='CLOSED' AND closed_at>=? AND closed_at<? AND ABS(COALESCE(result_value,0))<0.0000001", (start_iso, end_iso)
        ).fetchone()[0])
        forex_closed = int(con.execute(
            "SELECT COUNT(*) FROM signals WHERE status='CLOSED' AND market_type='FOREX' AND closed_at>=? AND closed_at<?", (start_iso, end_iso)
        ).fetchone()[0])
        crypto_closed = int(con.execute(
            "SELECT COUNT(*) FROM signals WHERE status='CLOSED' AND market_type='CRYPTO' AND closed_at>=? AND closed_at<?", (start_iso, end_iso)
        ).fetchone()[0])
        forex_pips = float(con.execute(
            "SELECT COALESCE(SUM(result_value),0) FROM signals WHERE status='CLOSED' AND market_type='FOREX' AND result_unit='PIPS' AND closed_at>=? AND closed_at<?", (start_iso, end_iso)
        ).fetchone()[0] or 0)
        crypto_pct = float(con.execute(
            "SELECT COALESCE(SUM(result_value),0) FROM signals WHERE status='CLOSED' AND market_type='CRYPTO' AND result_unit='PERCENT' AND closed_at>=? AND closed_at<?", (start_iso, end_iso)
        ).fetchone()[0] or 0)
        active_now = int(con.execute("SELECT COUNT(*) FROM signals WHERE status<>'CLOSED'").fetchone()[0])
        free_opened = int(con.execute(
            "SELECT COUNT(*) FROM signals WHERE created_at>=? AND created_at<? AND destination IN ('FREE','BOTH')", (start_iso, end_iso)
        ).fetchone()[0])
        vip_opened = int(con.execute(
            "SELECT COUNT(*) FROM signals WHERE created_at>=? AND created_at<? AND destination IN ('VIP','BOTH')", (start_iso, end_iso)
        ).fetchone()[0])
        new_users = int(con.execute(
            "SELECT COUNT(*) FROM users WHERE created_at>=? AND created_at<?", (start_iso, end_iso)
        ).fetchone()[0])
        approved_payments = int(con.execute(
            "SELECT COUNT(*) FROM payments WHERE status='approved' AND COALESCE(reviewed_at,created_at)>=? AND COALESCE(reviewed_at,created_at)<?", (start_iso, end_iso)
        ).fetchone()[0])
        rial_revenue = int(con.execute(
            "SELECT COALESCE(SUM(final_amount_irr),0) FROM payments WHERE status='approved' AND payment_method='rial' AND COALESCE(reviewed_at,created_at)>=? AND COALESCE(reviewed_at,created_at)<?", (start_iso, end_iso)
        ).fetchone()[0] or 0)
        revenue_usdt = float(con.execute(
            "SELECT COALESCE(SUM(amount_usdt),0) FROM payments WHERE status='approved' AND COALESCE(reviewed_at,created_at)>=? AND COALESCE(reviewed_at,created_at)<?", (start_iso, end_iso)
        ).fetchone()[0] or 0)
        usdt_payments = int(con.execute(
            "SELECT COUNT(*) FROM payments WHERE status='approved' AND payment_method='usdt' AND COALESCE(reviewed_at,created_at)>=? AND COALESCE(reviewed_at,created_at)<?", (start_iso, end_iso)
        ).fetchone()[0])
        vip_activations = int(con.execute(
            "SELECT COUNT(*) FROM licenses WHERE created_at>=? AND created_at<?", (start_iso, end_iso)
        ).fetchone()[0])

        def extreme(market: str, direction: str):
            order = "DESC" if direction == "best" else "ASC"
            return con.execute(
                f"SELECT code,symbol,direction,result_value,result_unit FROM signals WHERE status='CLOSED' AND market_type=? AND closed_at>=? AND closed_at<? AND result_value IS NOT NULL ORDER BY result_value {order} LIMIT 1",
                (market, start_iso, end_iso),
            ).fetchone()

        return {
            'opened': opened, 'closed': closed, 'wins': wins, 'losses': losses, 'be': be,
            'win_rate': round((wins / closed * 100) if closed else 0, 1),
            'forex_closed': forex_closed, 'crypto_closed': crypto_closed,
            'forex_pips': round(forex_pips, 1), 'crypto_pct': round(crypto_pct, 2),
            'active_now': active_now, 'free_opened': free_opened, 'vip_opened': vip_opened,
            'new_users': new_users, 'approved_payments': approved_payments,
            'rial_revenue': rial_revenue, 'usdt_payments': usdt_payments,
            'vip_activations': vip_activations,
            'best_forex': extreme('FOREX','best'), 'worst_forex': extreme('FOREX','worst'),
            'best_crypto': extreme('CRYPTO','best'), 'worst_crypto': extreme('CRYPTO','worst'),
        }



def channel_performance_stats(start_iso: str, end_iso: str, channel: str) -> dict:
    """Closed-trade performance for one publication channel. BOTH counts in each channel.

    Net percent is the sum of direction-aware raw price returns. It intentionally does
    not apply leverage or lot sizing so Forex and Crypto remain comparable.
    """
    channel = channel.upper()
    allowed = ("FREE", "BOTH") if channel == "FREE" else ("VIP", "BOTH")
    with conn() as con:
        rows = list(con.execute(
            """SELECT direction,entry_price,exit_price,result_value
               FROM signals
               WHERE status='CLOSED' AND closed_at>=? AND closed_at<?
                 AND destination IN (?,?)
               ORDER BY closed_at""",
            (start_iso, end_iso, allowed[0], allowed[1])
        ).fetchall())
    wins = losses = be = 0
    net_pct = 0.0
    for row in rows:
        rv = float(row["result_value"] or 0)
        if rv > 0: wins += 1
        elif rv < 0: losses += 1
        else: be += 1
        entry = float(row["entry_price"] or 0)
        exit_price = float(row["exit_price"] or 0)
        if entry:
            direction = str(row["direction"] or "").upper()
            delta = (exit_price-entry) if direction in {"BUY","LONG"} else (entry-exit_price)
            net_pct += (delta/entry)*100
    total = len(rows)
    return {
        "total": total, "wins": wins, "losses": losses, "be": be,
        "win_rate": round((wins/total*100) if total else 0, 1),
        "net_pct": round(net_pct, 2),
    }

def channel_market_performance_stats(start_iso: str, end_iso: str, channel: str, market: str) -> dict:
    """Closed-trade performance for one publication channel and one market.

    BOTH signals count in both Free and VIP channel views, matching publication
    behavior. Crypto result is summed as PERCENT; Forex result is summed as PIPS.
    No leverage, lot sizing, spread, commission, or account-P&L conversion is
    applied here.
    """
    channel = channel.upper()
    market = market.upper()
    if channel not in {"FREE", "VIP"}:
        raise ValueError("channel must be FREE or VIP")
    if market not in {"FOREX", "CRYPTO"}:
        raise ValueError("market must be FOREX or CRYPTO")

    allowed = ("FREE", "BOTH") if channel == "FREE" else ("VIP", "BOTH")
    expected_unit = "PIPS" if market == "FOREX" else "PERCENT"
    with conn() as con:
        rows = list(con.execute(
            """SELECT result_value,result_unit
               FROM signals
               WHERE status='CLOSED' AND closed_at>=? AND closed_at<?
                 AND destination IN (?,?) AND market_type=?
               ORDER BY closed_at""",
            (start_iso, end_iso, allowed[0], allowed[1], market),
        ).fetchall())

    wins = losses = be = 0
    result_total = 0.0
    for row in rows:
        rv = float(row["result_value"] or 0)
        if rv > 0:
            wins += 1
        elif rv < 0:
            losses += 1
        else:
            be += 1
        if str(row["result_unit"] or "").upper() == expected_unit:
            result_total += rv

    total = len(rows)
    base = {
        "total": total,
        "wins": wins,
        "losses": losses,
        "be": be,
        "win_rate": round((wins / total * 100) if total else 0, 1),
    }
    if market == "FOREX":
        base["result_pips"] = round(result_total, 1)
        base["result_pct"] = 0.0
    else:
        base["result_pct"] = round(result_total, 2)
        base["result_pips"] = 0.0
    return base


def report_was_sent(report_type: str, period_key: str, recipient_id) -> bool:
    with conn() as con:
        return con.execute(
            "SELECT 1 FROM report_dispatches WHERE report_type=? AND period_key=? AND recipient_id=?",
            (report_type, period_key, recipient_id),
        ).fetchone() is not None


def claim_report_dispatch(report_type: str, period_key: str, recipient_id, period_start: str, period_end: str) -> bool:
    """Atomically reserve a report delivery so parallel bot processes cannot double-send it."""
    with conn() as con:
        cur=con.execute(
            "INSERT OR IGNORE INTO report_dispatches(report_type,period_key,recipient_id,period_start,period_end,sent_at) VALUES(?,?,?,?,?,?)",
            (report_type, period_key, recipient_id, period_start, period_end, "PENDING"),
        )
        return cur.rowcount == 1


def release_report_dispatch(report_type: str, period_key: str, recipient_id) -> None:
    with conn() as con:
        con.execute("DELETE FROM report_dispatches WHERE report_type=? AND period_key=? AND recipient_id=? AND sent_at='PENDING'",
                    (report_type, period_key, recipient_id))


def mark_report_sent(report_type: str, period_key: str, recipient_id, period_start: str, period_end: str) -> None:
    with conn() as con:
        con.execute(
            """INSERT INTO report_dispatches(report_type,period_key,recipient_id,period_start,period_end,sent_at) VALUES(?,?,?,?,?,?)
               ON CONFLICT(report_type,period_key,recipient_id) DO UPDATE SET period_start=excluded.period_start,period_end=excluded.period_end,sent_at=excluded.sent_at""",
            (report_type, period_key, recipient_id, period_start, period_end, now_iso()),
        )


def exchange_account(telegram_id: int):
    with conn() as con:
        return con.execute("SELECT * FROM autotrade_exchange_accounts WHERE telegram_id=?", (telegram_id,)).fetchone()


def set_exchange_account_placeholder(telegram_id: int, exchange: str, *, status: str = "setup_required"):
    now = now_iso()
    exchange = str(exchange or "").strip().lower()
    if not exchange:
        raise ValueError("exchange is required")
    with conn() as con:
        con.execute(
            """INSERT INTO autotrade_exchange_accounts(telegram_id,exchange,status,bound_at)
               VALUES(?,?,?,?)
               ON CONFLICT(telegram_id) DO UPDATE SET exchange=excluded.exchange,status=excluded.status,bound_at=excluded.bound_at""",
            (telegram_id, exchange, status, now),
        )
        return con.execute("SELECT * FROM autotrade_exchange_accounts WHERE telegram_id=?", (telegram_id,)).fetchone()


def save_exchange_account(telegram_id: int, exchange: str, api_key_enc: str, api_secret_enc: str, api_passphrase_enc: str = "", *, account_label: str = "", status: str = "connected"):
    now = now_iso()
    exchange = str(exchange or "").strip().lower()
    with conn() as con:
        con.execute(
            """INSERT INTO autotrade_exchange_accounts(telegram_id,exchange,api_key_enc,api_secret_enc,api_passphrase_enc,account_label,status,bound_at,last_seen_at)
               VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(telegram_id) DO UPDATE SET
                 exchange=excluded.exchange,api_key_enc=excluded.api_key_enc,api_secret_enc=excluded.api_secret_enc,
                 api_passphrase_enc=excluded.api_passphrase_enc,account_label=excluded.account_label,status=excluded.status,
                 bound_at=excluded.bound_at,last_seen_at=excluded.last_seen_at""",
            (telegram_id, exchange, api_key_enc, api_secret_enc, api_passphrase_enc, account_label, status, now, now),
        )
        return con.execute("SELECT * FROM autotrade_exchange_accounts WHERE telegram_id=?", (telegram_id,)).fetchone()


def disconnect_exchange_account(telegram_id: int) -> None:
    with conn() as con:
        con.execute("DELETE FROM autotrade_exchange_accounts WHERE telegram_id=?", (telegram_id,))


def autotrade_user_signal_receipts(telegram_id: int, *, limit: int = 20, open_only: bool = False):
    """Return a unified Auto Trade history.

    Traditional signal receipts remain supported. Manual MT5 executions are
    merged from the execution ledger so a real trade is visible even when it
    was never created through the Telegram signal-receipt path.
    """
    with conn() as con:
        q = """SELECT r.*, s.code, s.symbol, s.direction, s.market_type, s.status AS signal_status,
                      s.entry_price, s.exit_price, s.result_value, s.result_unit, s.trailing_code, s.created_at
               FROM autotrade_signal_receipts r JOIN signals s ON s.id=r.signal_id
               WHERE r.telegram_id=?"""
        args=[int(telegram_id)]
        if open_only:
            q += " AND lower(r.status) IN ('executed','open','seen') AND s.status NOT IN ('CLOSED','CANCELLED')"
        q += " ORDER BY r.first_seen_at DESC LIMIT ?"
        args.append(max(1,min(int(limit),100)))
        receipt_rows=[dict(x) for x in con.execute(q,tuple(args)).fetchall()]

        executions=con.execute(
            """SELECT e.*, s.code, s.status AS signal_status, s.entry_price AS signal_entry_price,
                      s.exit_price AS signal_exit_price, s.result_value AS signal_result_value,
                      s.result_unit AS signal_result_unit, s.trailing_code
               FROM autotrade_trade_executions e
               LEFT JOIN signals s ON s.id=e.signal_id
               WHERE e.telegram_id=? ORDER BY e.created_at DESC, e.id DESC""",
            (int(telegram_id),)
        ).fetchall()

    # Collapse lifecycle events into one customer-facing position row per ticket.
    grouped={}
    for e in executions:
        ticket=str(e["ticket"])
        g=grouped.setdefault(ticket,{"open":None,"close":None,"latest":e})
        typ=str(e["event_type"]).upper()
        if typ=="OPEN" and g["open"] is None:
            g["open"]=e
        if typ=="CLOSE" and g["close"] is None:
            g["close"]=e

    receipt_tickets={str(r.get("ticket")) for r in receipt_rows if r.get("ticket")}
    for ticket,g in grouped.items():
        if ticket in receipt_tickets:
            continue
        if open_only and g["close"] is not None:
            continue
        e=g["open"] or g["latest"]
        c=g["close"]
        row={
            "signal_id": e["signal_id"],
            "code": e["code"] or f"MT5-{ticket}",
            "symbol": e["symbol"] or "—",
            "direction": e["direction"] or "—",
            "market_type": None,
            "status": "CLOSED" if c else ("OPEN" if g["open"] else str(e["status"]).upper()),
            "signal_status": e["signal_status"],
            "entry_price": e["entry_price"] or e["signal_entry_price"],
            "exit_price": c["exit_price"] if c else e["signal_exit_price"],
            "result_value": c["profit"] if c else e["signal_result_value"],
            "result_unit": "USD" if c else e["signal_result_unit"],
            "trailing_code": e["trailing_code"] or "Manual MT5",
            "ticket": ticket,
            "first_seen_at": e["created_at"],
        }
        receipt_rows.append(row)

    receipt_rows.sort(key=lambda r: str(r.get("first_seen_at") or r.get("created_at") or ""), reverse=True)
    return receipt_rows[:max(1,min(int(limit),100))]


def autotrade_user_daily_stats(telegram_id: int, start_iso: str, end_iso: str):
    # Financial/reporting truth comes from the execution ledger, not Telegram
    # delivery. Prefer the unified current-cycle report when the requested window
    # covers the current cycle; preserve the legacy keys for UI compatibility.
    rows = autotrade_trade_executions(telegram_id, start_iso=start_iso, end_iso=end_iso, limit=2000)
    opens = [r for r in rows if str(r["event_type"]).upper() == "OPEN"]
    closes = [r for r in rows if str(r["event_type"]).upper() == "CLOSE"]
    wins = sum(1 for r in closes if float(r["profit"] or 0) > 0)
    losses = sum(1 for r in closes if float(r["profit"] or 0) < 0)
    be = sum(1 for r in closes if abs(float(r["profit"] or 0)) < 1e-12)
    return {
        "total": len(opens),
        "executed": sum(1 for r in opens if str(r["status"]).upper() not in {"FAILED","IGNORED"}),
        "closed": len(closes),
        "wins": wins,
        "losses": losses,
        "be": be,
        "net_pnl": round(sum(float(r["profit"] or 0) for r in closes), 2),
        "gross_pnl": round(sum(float(r["gross_profit"] or r["profit"] or 0) for r in closes), 2),
        "commission": round(sum(float(r["commission"] or 0) for r in closes), 2),
        "swap": round(sum(float(r["swap"] or 0) for r in closes), 2),
        "cycle_id": current_cycle_id(),
    }

def deactivate_expired_entitlements(license_id: int) -> tuple[bool, bool]:
    """Mark expired entitlement flags off while keeping the row alive for the other entitlement."""
    now = now_iso()
    with conn() as con:
        row=con.execute("SELECT * FROM licenses WHERE id=?",(license_id,)).fetchone()
        if not row: return False,False
        vip_expired=bool(row["vip_access"]) and bool(row["vip_expires_at"]) and str(row["vip_expires_at"])<=now
        auto_expired=bool(row["autotrade_access"]) and bool(row["autotrade_expires_at"]) and str(row["autotrade_expires_at"])<=now
        if vip_expired: con.execute("UPDATE licenses SET vip_access=0 WHERE id=?",(license_id,))
        if auto_expired: con.execute("UPDATE licenses SET autotrade_access=0 WHERE id=?",(license_id,))
        return vip_expired,auto_expired


def get_autotrade_command(command_id: int):
    with conn() as con:
        return con.execute("SELECT * FROM autotrade_commands WHERE id=?",(command_id,)).fetchone()
