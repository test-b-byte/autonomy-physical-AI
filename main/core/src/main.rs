mod belief_map;
mod dead_reckoning;
mod engine;
mod hazard;
mod path_planner;
mod sensor_model;
mod server;
mod sim;

use std::sync::Arc;
use tokio::sync::Mutex;

use server::{AppState, SharedState};

#[tokio::main]
async fn main() {
    env_logger::Builder::from_env(
        env_logger::Env::default().default_filter_or("info"),
    ).init();

    // `--sim` runs the scripted scenario and exits.
    if std::env::args().any(|a| a == "--sim") {
        sim::run();
        return;
    }

    let state: SharedState = Arc::new(AppState {
        engine: Mutex::new(engine::GhostEngine::new()),
    });

    let app       = server::router(state);
    let bind_addr = std::env::var("GHOST_ADDR").unwrap_or_else(|_| "0.0.0.0:9001".into());

    log::info!("GHOST core  ws://{bind_addr}/ws");
    log::info!("health      http://{bind_addr}/health");
    log::info!("sim mode    cargo run -- --sim");

    let listener = tokio::net::TcpListener::bind(&bind_addr).await
        .unwrap_or_else(|e| panic!("cannot bind {bind_addr}: {e}"));

    axum::serve(listener, app).await.unwrap();
}
