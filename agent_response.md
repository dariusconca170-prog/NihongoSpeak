```json
[
{
"path": "Cargo.toml",
"content": "[package]\nname = \"hello-world\"\nversion = \"1.0.0\"\nedition = \"2021\"\nauthors = [\"Developer <dev@example.com>\"]\ndescription = \"A production-ready Hello World application\"\nlicense = \"MIT\"\n\n[dependencies]\nanyhow = \"1.0\"\ntracing = \"0.1\"\ntracing-subscriber = { version = \"0.3\", features = [\"env-filter\"] }\n\n[profile.release]\nlto = true\ncodegen-units = 1\npanic = \"abort\"\nstrip = true\n"
},
{
"path": "src/main.rs",
"content": "use anyhow::{Context, Result};\nuse tracing::{error, info};\n\nfn main() {\n    if let Err(e) = run() {\n        error!(\"Application error: {e}\");\n        std::process::exit(1);\n    }\n}\n\nfn run() -> Result<()> {\n    tracing_subscriber::fmt()\n        .with_env_filter(\n            tracing_subscriber::EnvFilter::try_from_default_env()\n                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new(\"info\")),\n        )\n        .init();\n\n    info!(\"Starting Hello World application\");\n\n    let message = get_greeting()\n        .context(\"Failed to get greeting message\")?;\n\n    println!(\"{}\", message);\n    info!(\"Successfully printed greeting\");\n\n    Ok(())\n}\n\nfn get_greeting() -> Result<String> {\n    let greeting = std::env::var(\"GREETING\").unwrap_or_else(|_| \"Hello, World!\".to_string());\n    Ok(greeting)\n}\n\n#[cfg(test)]\nmod tests {\n    use super::*;\n\n    #[test]\n    fn test_get_greeting_default() {\n        std::env::remove_var(\"GREETING\");\n        assert_eq!(get_greeting().unwrap(), \"Hello, World!\");\n    }\n\n    #[test]\n    fn test_get_greeting_custom() {\n        std::env::set_var(\"GREETING\", \"Custom greeting\");\n        assert_eq!(get_greeting().unwrap(), \"Custom greeting\");\n        std::env::remove_var(\"GREETING\");\n    }\n}\n"
},
{
"path": "README.md",
"content": "# Hello World\n\nA production-ready Hello World application in Rust.\n\n## Features\n\n- Structured logging with tracing\n- Proper error handling with anyhow\n- Environment variable configuration\n- Release profile optimized for production\n\n## Usage\n\n```bash\n# Run normally\ncargo run\n\n# Run with custom greeting\nGREETING=\"Hello, Rust!\" cargo run\n\n# Run tests\ncargo test\n\n# Build for production\ncargo build --release\n```\n"
}
]
```