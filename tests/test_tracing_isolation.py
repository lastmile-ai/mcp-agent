"""Tests for per-app tracing isolation."""

import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from opentelemetry import trace

from mcp_agent.app import MCPApp
from mcp_agent.config import Settings, OpenTelemetrySettings
from mcp_agent.tracing.tracer import TracingConfig


class TestTracingIsolation:
    """Test cases for per-app tracing isolation."""

    @pytest.fixture
    def otel_settings(self):
        """Create OpenTelemetry settings."""
        return OpenTelemetrySettings(
            enabled=True, service_name="test_service", exporters=["console"]
        )

    @pytest.fixture
    def settings_with_otel(self, otel_settings):
        """Create settings with OTEL enabled."""
        return Settings(otel=otel_settings)

    @pytest.fixture
    def settings_without_otel(self):
        """Create settings with OTEL disabled."""
        return Settings(
            otel=OpenTelemetrySettings(enabled=False, service_name="disabled_service")
        )

    @pytest.mark.asyncio
    async def test_tracing_config_instance_based(self, otel_settings):
        """Test that TracingConfig uses instance variables instead of class variables."""
        # Create two TracingConfig instances
        config1 = TracingConfig()
        config2 = TracingConfig()

        # They should have separate tracer providers
        assert config1._tracer_provider is None
        assert config2._tracer_provider is None

        # Configure the first one
        await config1.configure(otel_settings, session_id="session1")

        # First should have a provider, second should not
        assert config1._tracer_provider is not None
        assert config2._tracer_provider is None

    @pytest.mark.asyncio
    async def test_app_has_own_tracer_provider(self, settings_with_otel):
        """Test that each MCPApp instance has its own tracer provider."""
        app1 = MCPApp(name="app1", settings=settings_with_otel)
        app2 = MCPApp(name="app2", settings=settings_with_otel)

        # Initially, neither app should have a tracer provider
        assert app1._tracer_provider is None
        assert app2._tracer_provider is None

        # Initialize both apps
        async with app1.run():
            async with app2.run():
                # Both should have tracer providers
                assert app1._tracer_provider is not None
                assert app2._tracer_provider is not None

                # They should be different instances
                assert app1._tracer_provider is not app2._tracer_provider

    @pytest.mark.asyncio
    async def test_cleanup_restores_provider(self, settings_with_otel):
        """Test that cleanup restores the original tracer provider state."""
        # Mock the cleanup_context to verify it's called correctly
        with patch("mcp_agent.app.cleanup_context", AsyncMock()) as mock_cleanup:
            app = MCPApp(name="test_app", settings=settings_with_otel)

            async with app.run():
                pass

            # Verify cleanup_context was called with shutdown_logger=False
            mock_cleanup.assert_called_once_with(shutdown_logger=False)

    @pytest.mark.asyncio
    async def test_context_stores_tracing_config(self, settings_with_otel):
        """Test that Context stores TracingConfig instance."""
        app = MCPApp(name="test_app", settings=settings_with_otel)

        async with app.run():
            # Context should have tracing_config
            assert app._context.tracing_config is not None
            assert isinstance(app._context.tracing_config, TracingConfig)

            # Context should have the tracer from the config
            assert app._context.tracer is not None
            assert app._context.tracing_enabled is True

    @pytest.mark.asyncio
    async def test_otel_disabled_no_tracing(self, settings_without_otel):
        """Test that when OTEL is disabled, no tracing is configured."""
        app = MCPApp(name="test_app", settings=settings_without_otel)

        async with app.run():
            # Should not have tracing configured
            assert app._tracer_provider is None
            assert app._context.tracing_config is None
            assert app._context.tracing_enabled is False

    @pytest.mark.asyncio
    async def test_global_provider_set_only_once(self, settings_with_otel):
        """Test that the global tracer provider is only set once."""
        # Reset the class variable for this test
        TracingConfig._global_provider_set = False

        # Mock trace.set_tracer_provider to track calls
        with patch(
            "mcp_agent.tracing.tracer.trace.set_tracer_provider"
        ) as mock_set_provider:
            with patch(
                "mcp_agent.tracing.tracer.trace.get_tracer_provider",
                return_value=trace.ProxyTracerProvider(),
            ):
                app1 = MCPApp(name="app1", settings=settings_with_otel)
                app2 = MCPApp(name="app2", settings=settings_with_otel)

                async with app1.run():
                    async with app2.run():
                        # set_tracer_provider should only be called once
                        assert mock_set_provider.call_count == 1

    @pytest.mark.asyncio
    async def test_each_app_different_service_name(self):
        """Test that each app can have different service names in their resources."""
        settings1 = Settings(
            otel=OpenTelemetrySettings(
                enabled=True, service_name="service1", exporters=[]
            )
        )
        settings2 = Settings(
            otel=OpenTelemetrySettings(
                enabled=True, service_name="service2", exporters=[]
            )
        )

        app1 = MCPApp(name="app1", settings=settings1)
        app2 = MCPApp(name="app2", settings=settings2)

        async with app1.run():
            async with app2.run():
                # Get the resources from each provider
                provider1 = app1._context.tracing_config._tracer_provider
                provider2 = app2._context.tracing_config._tracer_provider

                if hasattr(provider1, "_resource") and hasattr(provider2, "_resource"):
                    service_name1 = provider1._resource.attributes.get("service.name")
                    service_name2 = provider2._resource.attributes.get("service.name")

                    assert service_name1 == "service1"
                    assert service_name2 == "service2"

    @pytest.mark.asyncio
    async def test_instrumentation_initialized_once(self, settings_with_otel):
        """Test that autoinstrumentation is only initialized once globally."""
        # Reset for this test
        TracingConfig._instrumentation_initialized = False

        # Mock the instrumentors at the import level
        mock_anthropic_class = MagicMock()
        mock_anthropic_instance = MagicMock()
        mock_anthropic_instance.is_instrumented_by_opentelemetry = False
        mock_anthropic_class.return_value = mock_anthropic_instance

        mock_openai_class = MagicMock()
        mock_openai_instance = MagicMock()
        mock_openai_instance.is_instrumented_by_opentelemetry = False
        mock_openai_class.return_value = mock_openai_instance

        # Patch at the module import level
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.instrumentation.anthropic": MagicMock(
                    AnthropicInstrumentor=mock_anthropic_class
                ),
                "opentelemetry.instrumentation.openai": MagicMock(
                    OpenAIInstrumentor=mock_openai_class
                ),
            },
        ):
            app1 = MCPApp(name="app1", settings=settings_with_otel)
            app2 = MCPApp(name="app2", settings=settings_with_otel)

            async with app1.run():
                # First app should trigger instrumentation
                mock_anthropic_instance.instrument.assert_called_once()
                mock_openai_instance.instrument.assert_called_once()

                # Reset the mocks
                mock_anthropic_instance.instrument.reset_mock()
                mock_openai_instance.instrument.reset_mock()

                async with app2.run():
                    # Second app should not trigger instrumentation again
                    mock_anthropic_instance.instrument.assert_not_called()
                    mock_openai_instance.instrument.assert_not_called()

    @pytest.mark.asyncio
    async def test_concurrent_apps_isolation(self, settings_with_otel):
        """Test that concurrent apps maintain isolation."""
        import asyncio

        results = {}

        async def run_app(name: str, service_name: str):
            """Run an app and store its provider ID."""
            settings = Settings(
                otel=OpenTelemetrySettings(
                    enabled=True, service_name=service_name, exporters=[]
                )
            )
            app = MCPApp(name=name, settings=settings)

            async with app.run():
                if app._context.tracing_config:
                    results[name] = {
                        "provider_id": id(app._context.tracing_config._tracer_provider),
                        "service_name": service_name,
                    }
                await asyncio.sleep(0.01)  # Simulate some work

        # Run multiple apps concurrently
        await asyncio.gather(
            run_app("app1", "service1"),
            run_app("app2", "service2"),
            run_app("app3", "service3"),
        )

        # Verify all apps ran and had different providers
        assert len(results) == 3
        provider_ids = [r["provider_id"] for r in results.values()]
        assert len(set(provider_ids)) == 3  # All different

    @pytest.mark.asyncio
    async def test_get_tracer_method(self, otel_settings):
        """Test the get_tracer method on TracingConfig."""
        config = TracingConfig()

        # Before configuration, should use global tracer
        tracer1 = config.get_tracer("test")
        assert tracer1 is not None

        # After configuration, should use the provider's tracer
        await config.configure(otel_settings, session_id="test_session")
        tracer2 = config.get_tracer("test")
        assert tracer2 is not None

        # Should be from the configured provider
        if config._tracer_provider:
            expected_tracer = config._tracer_provider.get_tracer("test")
            assert type(tracer2) is type(expected_tracer)

    @pytest.mark.asyncio
    async def test_cleanup_context_with_shutdown_logger(self):
        """Test cleanup_context with shutdown_logger parameter."""
        from mcp_agent.core.context import cleanup_context

        # Mock LoggingConfig.shutdown
        with patch(
            "mcp_agent.core.context.LoggingConfig.shutdown", AsyncMock()
        ) as mock_shutdown:
            # Test with shutdown_logger=True
            await cleanup_context(shutdown_logger=True)
            mock_shutdown.assert_called_once()

            # Reset mock
            mock_shutdown.reset_mock()

            # Test with shutdown_logger=False
            await cleanup_context(shutdown_logger=False)
            mock_shutdown.assert_not_called()

    @pytest.mark.asyncio
    async def test_file_span_exporter_isolation(self):
        """Test that multiple apps can write to different trace files."""
        import tempfile
        import json
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create settings for two apps with different trace files
            trace_file1 = Path(tmpdir) / "app1_traces.jsonl"
            trace_file2 = Path(tmpdir) / "app2_traces.jsonl"

            settings1 = Settings(
                otel=OpenTelemetrySettings(
                    enabled=True,
                    service_name="app1-service",
                    exporters=["file"],
                    path=str(trace_file1),  # Direct path
                )
            )

            settings2 = Settings(
                otel=OpenTelemetrySettings(
                    enabled=True,
                    service_name="app2-service",
                    exporters=["file"],
                    path=str(trace_file2),  # Direct path
                )
            )

            # Create and run both apps
            app1 = MCPApp(name="app1", settings=settings1)
            app2 = MCPApp(name="app2", settings=settings2)

            async with app1.run():
                async with app2.run():
                    # Get tracers and create spans
                    tracer1 = app1._context.tracer
                    tracer2 = app2._context.tracer

                    if tracer1:
                        with tracer1.start_as_current_span("test_span_app1"):
                            pass

                    if tracer2:
                        with tracer2.start_as_current_span("test_span_app2"):
                            pass

            # Verify trace files were created
            # The cleanup in the context manager will flush traces
            assert trace_file1.exists(), f"Trace file {trace_file1} should exist"
            assert trace_file2.exists(), f"Trace file {trace_file2} should exist"

            # Read and verify contents
            spans1 = []
            with open(trace_file1, "r") as f:
                for line in f:
                    if line.strip():
                        spans1.append(json.loads(line))

            spans2 = []
            with open(trace_file2, "r") as f:
                for line in f:
                    if line.strip():
                        spans2.append(json.loads(line))

            # Verify spans are from correct services
            assert len(spans1) > 0, "App1 should have generated spans"
            assert len(spans2) > 0, "App2 should have generated spans"

            for span in spans1:
                resource = span.get("resource", {})
                attributes = resource.get("attributes", {})
                assert attributes.get("service.name") == "app1-service"

            for span in spans2:
                resource = span.get("resource", {})
                attributes = resource.get("attributes", {})
                assert attributes.get("service.name") == "app2-service"

    @pytest.mark.asyncio
    async def test_file_span_exporter_with_path_settings(self):
        """Test FileSpanExporter with TracePathSettings when path is not set."""
        import tempfile
        import json
        from pathlib import Path
        from mcp_agent.config import TracePathSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            # Use path_settings instead of direct path
            path_settings = TracePathSettings(
                path_pattern=f"{tmpdir}/traces-{{unique_id}}.jsonl",
                unique_id="session_id",
            )

            settings = Settings(
                otel=OpenTelemetrySettings(
                    enabled=True,
                    service_name="path-settings-service",
                    exporters=["file"],
                    path_settings=path_settings,
                    # Note: path is NOT set, so path_settings should be used
                )
            )

            app = MCPApp(name="path-settings-app", settings=settings)

            async with app.run():
                # Create a span
                if app._context.tracer:
                    with app._context.tracer.start_as_current_span("test_span"):
                        pass

                # Expected file based on session_id
                session_id = app.session_id
                expected_file = Path(tmpdir) / f"traces-{session_id}.jsonl"

            # Give exporter time to write
            await asyncio.sleep(0.5)

            # Verify the correct file was created
            assert expected_file.exists(), f"Expected trace file at {expected_file}"

            # Verify it contains spans
            with open(expected_file, "r") as f:
                spans = [json.loads(line) for line in f if line.strip()]

            assert len(spans) > 0, "Should have generated spans"

            # Verify service name
            for span in spans:
                resource = span.get("resource", {})
                attributes = resource.get("attributes", {})
                assert attributes.get("service.name") == "path-settings-service"

    @pytest.mark.asyncio
    async def test_force(self, otel_settings):
        """Test that force allows reconfiguration of TracingConfig."""
        config = TracingConfig()

        # First configuration
        await config.configure(otel_settings, session_id="session1")
        provider1 = config._tracer_provider
        assert provider1 is not None

        # Try to configure again without force - should skip
        await config.configure(otel_settings, session_id="session2")
        assert config._tracer_provider is provider1  # Same provider

        # Configure with force=True
        await config.configure(otel_settings, session_id="session3", force=True)
        provider2 = config._tracer_provider
        assert provider2 is not None
        assert provider2 is not provider1  # Different provider

    @pytest.mark.asyncio
    async def test_concurrent_apps_different_trace_files(self):
        """Test that concurrent apps write to different trace files without interference."""
        import tempfile
        import asyncio
        import json
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            trace_files = []

            async def run_app_with_traces(app_num: int):
                """Run an app and generate traces."""
                trace_file = Path(tmpdir) / f"concurrent_{app_num}.jsonl"
                trace_files.append((app_num, trace_file))

                settings = Settings(
                    otel=OpenTelemetrySettings(
                        enabled=True,
                        service_name=f"concurrent-app-{app_num}",
                        exporters=["file"],
                        path=str(trace_file),
                    )
                )

                app = MCPApp(name=f"concurrent-{app_num}", settings=settings)

                async with app.run():
                    # Generate some spans
                    if app._context.tracer:
                        for i in range(3):
                            with app._context.tracer.start_as_current_span(f"span_{i}"):
                                await asyncio.sleep(0.01)

            # Run 5 apps concurrently
            await asyncio.gather(*[run_app_with_traces(i) for i in range(5)])

            # Give exporters time to flush
            await asyncio.sleep(0.5)

            # Verify all trace files exist and contain correct data
            for app_num, trace_file in trace_files:
                assert trace_file.exists(), f"Trace file for app {app_num} should exist"

                # Read spans
                spans = []
                with open(trace_file, "r") as f:
                    for line in f:
                        if line.strip():
                            spans.append(json.loads(line))

                # Verify spans are present and from correct service
                assert len(spans) >= 3, f"App {app_num} should have at least 3 spans"

                for span in spans:
                    resource = span.get("resource", {})
                    attributes = resource.get("attributes", {})
                    service_name = attributes.get("service.name")
                    assert service_name == f"concurrent-app-{app_num}", (
                        f"Span should be from concurrent-app-{app_num}, got {service_name}"
                    )
