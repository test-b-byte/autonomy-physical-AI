/// Scripted demo scenario — runs without hardware.
/// Prints a coloured ASCII heatmap + state to stdout after each step.
/// Run with: `cargo run -- --sim`

use crate::engine::{GhostEngine, IncomingMsg};
use crate::sensor_model::SensorType;

pub fn run() {
    let mut eng = GhostEngine::new();

    println!("\n╔══════════════════════════════════════╗");
    println!("║   GHOST — Bayesian SAR Demo          ║");
    println!("╚══════════════════════════════════════╝\n");

    // ── 1. Configure 20×20 grid, 2 m/cell, LKP at centre ─────────────────
    step(&mut eng, "CONFIGURE  20×20 grid · LKP=(20m,20m) · σ=12m", IncomingMsg::Config {
        width: 20, height: 20, cell_size_m: 2.0,
        last_known_x: 20.0, last_known_y: 20.0,
        prior_sigma_m: Some(12.0),
        sensor_specs: None,
    });

    // ── 2. Robot moves NE — negative sweeps shift mass SW ─────────────────
    for (i, (wx, wy)) in [(2.0,2.0),(4.0,4.0),(6.0,6.0),(8.0,8.0)].iter().enumerate() {
        step(&mut eng, &format!("MOVE  robot → ({wx},{wy})"), IncomingMsg::Teleport { x: *wx, y: *wy });
        step(&mut eng,
            &format!("SWEEP #{} — all sensors: no detection", i + 1),
            sensor_msg(SensorType::Thermal,  false, 0.90));
        step(&mut eng, "",
            sensor_msg(SensorType::Ir,       false, 0.95));
        step(&mut eng, "",
            sensor_msg(SensorType::Acoustic, false, 0.80));
        step(&mut eng, "",
            sensor_msg(SensorType::Vision,   false, 0.85));
    }

    // ── 3. Robot moves toward LKP area ────────────────────────────────────
    step(&mut eng, "MOVE  robot → (18m, 18m) — closing on last-known position",
        IncomingMsg::Teleport { x: 18.0, y: 18.0 });

    // ── 4. Thermal hit ─────────────────────────────────────────────────────
    step(&mut eng, "THERMAL  heat signature detected — confidence 0.80",
        sensor_msg(SensorType::Thermal, true, 0.80));

    // ── 5. Vision confirms ─────────────────────────────────────────────────
    step(&mut eng, "VISION   human silhouette confirmed — confidence 0.85",
        sensor_msg(SensorType::Vision, true, 0.85));

    // ── 6. Acoustic confirms ───────────────────────────────────────────────
    step(&mut eng, "ACOUSTIC voice frequency band detected — confidence 0.75",
        sensor_msg(SensorType::Acoustic, true, 0.75));

    // ── 7. IR close-range lock ────────────────────────────────────────────
    step(&mut eng, "IR       close-range lock — confidence 0.95",
        sensor_msg(SensorType::Ir, true, 0.95));

    // ── Final state ────────────────────────────────────────────────────────
    let snap = eng.snapshot();
    println!("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    if let Some(c) = &snap.contact {
        println!("🎯  CONTACT  cell({},{})  world({:.1}m, {:.1}m)",
            c.cell_x, c.cell_y, c.world_x, c.world_y);
        println!("    P={:.3}  confidence={:.3}  sensors={:?}",
            c.probability, c.combined_confidence, c.sensors);
    } else {
        println!("No contact yet — continue search.");
    }
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
}

fn sensor_msg(sensor_type: SensorType, detection: bool, confidence: f64) -> IncomingMsg {
    IncomingMsg::Sensor { sensor_type, detection, confidence }
}

fn step(eng: &mut GhostEngine, label: &str, msg: IncomingMsg) {
    eng.handle(msg);
    let snap = eng.snapshot();
    if !label.is_empty() {
        println!("\n▶  {label}");
    }
    print_heatmap(&snap.grid, snap.robot_cell, snap.next_waypoint);
    println!(
        "   robot=({:.1},{:.1})  next_wp={:?}  entropy={:.2}  peak={:.3}  sweeps={}",
        snap.robot_x, snap.robot_y,
        snap.next_waypoint,
        snap.entropy,
        snap.max_probability,
        snap.sweep_count,
    );
}

fn print_heatmap(
    grid: &[Vec<f64>],
    robot: [usize; 2],
    waypoint: Option<[usize; 2]>,
) {
    let symbols = [' ', '·', '+', 'o', 'O', '#', '@'];
    let max_p = grid.iter().flat_map(|r| r.iter()).cloned().fold(0.0_f64, f64::max);

    println!("   ┌{}┐", "─".repeat(grid[0].len() * 2));
    for (y, row) in grid.iter().enumerate() {
        print!("   │");
        for (x, &p) in row.iter().enumerate() {
            if [x, y] == robot {
                print!("R ");
            } else if waypoint == Some([x, y]) {
                print!("W ");
            } else {
                let idx = if max_p > 0.0 {
                    ((p / max_p) * (symbols.len() - 1) as f64) as usize
                } else { 0 };
                let sym = symbols[idx.min(symbols.len() - 1)];
                print!("{sym} ");
            }
        }
        println!("│");
    }
    println!("   └{}┘", "─".repeat(grid[0].len() * 2));
    println!("   R=robot  W=next waypoint  @=peak probability");
}
