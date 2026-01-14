use pyo3::prelude::*;
use serde::Deserialize;
use serde_json::json;

#[derive(Deserialize, Debug)]
struct SolvePayload {
    to_call_chips: Option<i64>,
    actor_commit_chips: Option<i64>,
    actor_stack_chips: Option<i64>,
    min_raise_to_chips: Option<i64>,
    max_raise_to_chips: Option<i64>,
    pot_chips: Option<i64>,
    equity_ppm: Option<i64>,
    players_alive: Option<i64>,
    street: Option<String>,
    rake_rate_ppm: Option<i64>,
    rake_cap_chips: Option<i64>,
    no_flop_no_drop: Option<bool>,
}

fn clamp_target(payload: &SolvePayload) -> i64 {
    let to_call = payload.to_call_chips.unwrap_or(0).max(0);
    let commit = payload.actor_commit_chips.unwrap_or(0).max(0);
    let stack = payload.actor_stack_chips.unwrap_or(0).max(0);
    let call_target = commit + to_call;

    // basic heuristic: raise 1.25x call, capped to 40% stack
    let mut target = call_target + ((to_call as f64 * 1.25).round() as i64);
    let cap = call_target + (stack as f64 * 0.4).round() as i64;
    if target > cap {
        target = cap;
    }
    if let Some(min_r) = payload.min_raise_to_chips {
        if target < min_r {
            target = min_r;
        }
    }
    if let Some(max_r) = payload.max_raise_to_chips {
        if target > max_r {
            target = max_r;
        }
    }
    target.max(call_target)
}

fn estimate_rake(
    pot_after: f64,
    street: Option<&str>,
    rake_rate_ppm: Option<i64>,
    rake_cap_chips: Option<i64>,
    no_flop_no_drop: Option<bool>,
) -> f64 {
    let rate = rake_rate_ppm.unwrap_or(0).max(0) as f64 / 1_000_000.0;
    let cap = rake_cap_chips.unwrap_or(0).max(0) as f64;
    let nfnd = no_flop_no_drop.unwrap_or(false);
    let street_val = street.unwrap_or("");
    if street_val.is_empty() || street_val == "PREFLOP" {
        if nfnd {
            return 0.0;
        }
        let cap_val = if cap > 0.0 { cap } else { pot_after };
        return (pot_after * rate).min(cap_val);
    }
    let mut rake = pot_after * rate;
    if cap > 0.0 {
        rake = rake.min(cap);
    }
    rake.max(0.0)
}

fn action_ev_call(
    equity: f64,
    pot_chips: i64,
    to_call: i64,
    street: Option<&str>,
    rake_rate_ppm: Option<i64>,
    rake_cap_chips: Option<i64>,
    no_flop_no_drop: Option<bool>,
) -> f64 {
    let pot_after = pot_chips.max(0) as f64 + to_call.max(0) as f64;
    let rake = estimate_rake(pot_after, street, rake_rate_ppm, rake_cap_chips, no_flop_no_drop);
    equity * (pot_after - rake).max(0.0) - (to_call.max(0) as f64)
}

fn action_ev_raise(
    equity: f64,
    pot_chips: i64,
    to_call: i64,
    target: i64,
    actor_commit: i64,
    players_alive: i64,
    street: Option<&str>,
    rake_rate_ppm: Option<i64>,
    rake_cap_chips: Option<i64>,
    no_flop_no_drop: Option<bool>,
) -> f64 {
    let pot_base = pot_chips.max(0) as f64;
    let commit = actor_commit.max(0);
    let bet_size = (target - commit).max(0) as f64;
    if bet_size <= 0.0 {
        return 0.0;
    }
    let rake_base = estimate_rake(pot_base + bet_size, street, rake_rate_ppm, rake_cap_chips, no_flop_no_drop);
    let denom = (pot_base + bet_size - rake_base).max(1.0);
    let defend_freq = (pot_base / denom).clamp(0.0, 1.0);
    let opponents = (players_alive - 1).max(1) as f64;
    let fold_all = (1.0 - defend_freq).powf(opponents);
    let exp_callers = defend_freq * opponents;
    let pot_after = pot_base + bet_size * (1.0 + exp_callers);
    let rake = estimate_rake(pot_after, street, rake_rate_ppm, rake_cap_chips, no_flop_no_drop);
    let ev_called = equity * (pot_after - rake).max(0.0) - bet_size;
    let rake_fold = estimate_rake(pot_base, street, rake_rate_ppm, rake_cap_chips, no_flop_no_drop);
    let ev_fold = (pot_base - rake_fold).max(0.0);
    fold_all * ev_fold + (1.0 - fold_all) * ev_called
}

#[pyfunction]
fn solve_json(payload: &str) -> PyResult<String> {
    let data: SolvePayload = serde_json::from_str(payload).map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
    let target = clamp_target(&data);
    let equity = data.equity_ppm.unwrap_or(0).max(0) as f64 / 1_000_000.0;
    let pot_chips = data.pot_chips.unwrap_or(0).max(0);
    let to_call = data.to_call_chips.unwrap_or(0).max(0);
    let players_alive = data.players_alive.unwrap_or(2).max(2);
    let street = data.street.as_deref();
    let call_ev = action_ev_call(
        equity,
        pot_chips,
        to_call,
        street,
        data.rake_rate_ppm,
        data.rake_cap_chips,
        data.no_flop_no_drop,
    );
    let raise_ev = action_ev_raise(
        equity,
        pot_chips,
        to_call,
        target,
        data.actor_commit_chips.unwrap_or(0),
        players_alive,
        street,
        data.rake_rate_ppm,
        data.rake_cap_chips,
        data.no_flop_no_drop,
    );
    let edge = raise_ev - call_ev;
    let suggested = if to_call > 0 {
        if edge > 0.0 { "RAISE" } else { "CALL" }
    } else if edge > 0.0 {
        "BET"
    } else {
        "CHECK"
    };
    let out = json!({
        "solver_schema_id": "postflop_solve_v1",
        "target_total_commit_chips": target,
        "call_ev": call_ev,
        "raise_ev": raise_ev,
        "raise_edge": edge,
        "suggested_action": suggested
    });
    Ok(out.to_string())
}

#[pymodule]
fn postflop_solver(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(solve_json, m)?)?;
    Ok(())
}
