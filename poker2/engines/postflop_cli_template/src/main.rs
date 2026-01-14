use postflop_solver::*;
use serde::Deserialize;
use std::env;
use std::fs;
use std::path::PathBuf;

#[derive(Deserialize)]
struct SolveSpec {
    card_config: CardConfigSpec,
    tree_config: TreeConfigSpec,
    solve_config: SolveConfigSpec,
    output: OutputSpec,
}

#[derive(Deserialize)]
struct CardConfigSpec {
    oop_range: String,
    ip_range: String,
    flop: String,
    turn: Option<String>,
    river: Option<String>,
}

#[derive(Deserialize, Clone)]
struct BetSizeSpec {
    bet: String,
    raise: String,
}

#[derive(Deserialize)]
struct TreeConfigSpec {
    initial_state: String,
    starting_pot: i32,
    effective_stack: i32,
    rake_rate: f64,
    rake_cap: f64,
    flop_bet_sizes: [BetSizeSpec; 2],
    turn_bet_sizes: [BetSizeSpec; 2],
    river_bet_sizes: [BetSizeSpec; 2],
    turn_donk_sizes: Option<String>,
    river_donk_sizes: Option<String>,
    add_allin_threshold: f64,
    force_allin_threshold: f64,
    merging_threshold: f64,
}

#[derive(Deserialize)]
struct SolveConfigSpec {
    max_iterations: u32,
    target_exploitability: f32,
    parallel: bool,
    allocate_compression: bool,
}

#[derive(Deserialize)]
struct OutputSpec {
    memo: Option<String>,
    compression_level: Option<i32>,
}

fn parse_board_state(value: &str) -> Result<BoardState, String> {
    match value {
        "flop" | "FLOP" => Ok(BoardState::Flop),
        "turn" | "TURN" => Ok(BoardState::Turn),
        "river" | "RIVER" => Ok(BoardState::River),
        _ => Err(format!("Unsupported initial_state: {}", value)),
    }
}

fn parse_bet_size(spec: &BetSizeSpec) -> Result<BetSizeOptions, String> {
    BetSizeOptions::try_from((spec.bet.as_str(), spec.raise.as_str()))
        .map_err(|e| format!("Invalid bet size options: {}", e))
}

fn parse_donk_size(value: &Option<String>) -> Result<Option<DonkSizeOptions>, String> {
    match value {
        None => Ok(None),
        Some(s) => DonkSizeOptions::try_from(s.as_str())
            .map(Some)
            .map_err(|e| format!("Invalid donk size options: {}", e)),
    }
}

fn parse_args() -> Result<(PathBuf, PathBuf), String> {
    let mut args = env::args().skip(1);
    let mut config_path: Option<PathBuf> = None;
    let mut output_path: Option<PathBuf> = None;

    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--config" => {
                let path = args.next().ok_or("--config requires a value")?;
                config_path = Some(PathBuf::from(path));
            }
            "--output" => {
                let path = args.next().ok_or("--output requires a value")?;
                output_path = Some(PathBuf::from(path));
            }
            _ => return Err(format!("Unknown argument: {}", arg)),
        }
    }

    let cfg = config_path.ok_or("Missing --config")?;
    let out = output_path.ok_or("Missing --output")?;
    Ok((cfg, out))
}

fn main() -> Result<(), String> {
    let (config_path, output_path) = parse_args()?;
    let config_text = fs::read_to_string(&config_path)
        .map_err(|e| format!("Failed to read config {}: {}", config_path.display(), e))?;
    let spec: SolveSpec = serde_json::from_str(&config_text)
        .map_err(|e| format!("Failed to parse config JSON: {}", e))?;

    let oop_range: Range = spec
        .card_config
        .oop_range
        .parse()
        .map_err(|e| format!("Invalid oop_range: {}", e))?;
    let ip_range: Range = spec
        .card_config
        .ip_range
        .parse()
        .map_err(|e| format!("Invalid ip_range: {}", e))?;
    let flop = flop_from_str(&spec.card_config.flop)
        .map_err(|_| "Invalid flop string".to_string())?;
    let turn = match &spec.card_config.turn {
        Some(card) => card_from_str(card).map_err(|_| "Invalid turn card".to_string())?,
        None => NOT_DEALT,
    };
    let river = match &spec.card_config.river {
        Some(card) => card_from_str(card).map_err(|_| "Invalid river card".to_string())?,
        None => NOT_DEALT,
    };
    let card_config = CardConfig {
        range: [oop_range, ip_range],
        flop,
        turn,
        river,
    };

    let tree_config = TreeConfig {
        initial_state: parse_board_state(&spec.tree_config.initial_state)?,
        starting_pot: spec.tree_config.starting_pot,
        effective_stack: spec.tree_config.effective_stack,
        rake_rate: spec.tree_config.rake_rate,
        rake_cap: spec.tree_config.rake_cap,
        flop_bet_sizes: [
            parse_bet_size(&spec.tree_config.flop_bet_sizes[0])?,
            parse_bet_size(&spec.tree_config.flop_bet_sizes[1])?,
        ],
        turn_bet_sizes: [
            parse_bet_size(&spec.tree_config.turn_bet_sizes[0])?,
            parse_bet_size(&spec.tree_config.turn_bet_sizes[1])?,
        ],
        river_bet_sizes: [
            parse_bet_size(&spec.tree_config.river_bet_sizes[0])?,
            parse_bet_size(&spec.tree_config.river_bet_sizes[1])?,
        ],
        turn_donk_sizes: parse_donk_size(&spec.tree_config.turn_donk_sizes)?,
        river_donk_sizes: parse_donk_size(&spec.tree_config.river_donk_sizes)?,
        add_allin_threshold: spec.tree_config.add_allin_threshold,
        force_allin_threshold: spec.tree_config.force_allin_threshold,
        merging_threshold: spec.tree_config.merging_threshold,
    };

    let action_tree = ActionTree::new(tree_config).map_err(|e| format!("Failed to build action tree: {}", e))?;
    let mut game = PostFlopGame::with_config(card_config, action_tree)
        .map_err(|e| format!("Failed to build game: {}", e))?;
    game.allocate_memory(spec.solve_config.allocate_compression);

    solve(
        &mut game,
        spec.solve_config.max_iterations,
        spec.solve_config.target_exploitability,
        spec.solve_config.parallel,
    );

    let memo = spec.output.memo.unwrap_or_default();
    save_data_to_file(&game, &memo, &output_path, spec.output.compression_level)
        .map_err(|e| format!("Failed to save output: {}", e))?;
    Ok(())
}
