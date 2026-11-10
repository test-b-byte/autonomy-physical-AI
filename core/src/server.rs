use axum::{
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        State,
    },
    response::IntoResponse,
    routing::get,
    Router,
};
use std::sync::Arc;
use tokio::sync::Mutex;
use tower_http::cors::{Any, CorsLayer};

use crate::engine::{GhostEngine, IncomingMsg};

pub struct AppState {
    pub engine: Mutex<GhostEngine>,
}

pub type SharedState = Arc<AppState>;

pub fn router(state: SharedState) -> Router {
    Router::new()
        .route("/ws",     get(ws_handler))
        .route("/health", get(|| async { "GHOST online" }))
        .layer(
            CorsLayer::new()
                .allow_origin(Any)
                .allow_methods(Any)
                .allow_headers(Any),
        )
        .with_state(state)
}

async fn ws_handler(
    ws: WebSocketUpgrade,
    State(state): State<SharedState>,
) -> impl IntoResponse {
    ws.on_upgrade(move |socket| handle_socket(socket, state))
}

async fn handle_socket(mut socket: WebSocket, state: SharedState) {
    // Push initial state on connect so the dashboard can render immediately.
    {
        let eng  = state.engine.lock().await;
        let snap = serde_json::to_string(&eng.snapshot()).unwrap();
        if socket.send(Message::Text(snap)).await.is_err() {
            return;
        }
    }

    // Request-response loop.
    // Python sensors: send IncomingMsg → receive StateSnapshot.
    // Dashboard: send {"type":"query"} every ~300 ms → receive StateSnapshot.
    while let Some(result) = socket.recv().await {
        match result {
            Ok(Message::Text(text)) => {
                match serde_json::from_str::<IncomingMsg>(&text) {
                    Ok(msg) => {
                        let snap = {
                            let mut eng = state.engine.lock().await;
                            eng.handle(msg);
                            serde_json::to_string(&eng.snapshot()).unwrap()
                        };
                        if socket.send(Message::Text(snap)).await.is_err() {
                            break;
                        }
                    }
                    Err(e) => log::warn!("bad message: {e} | raw: {text}"),
                }
            }
            Ok(Message::Close(_)) | Err(_) => break,
            _ => {}
        }
    }
}
