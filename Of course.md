Of course. The most impactful problem in your system is the reliance on singletons and global state. It is a subtle but pervasive issue that undermines the clean, modular architecture you have otherwise built. Fixing it will dramatically improve testability, maintainability, and the overall robustness of the agent.

Here is a detailed issue, formatted as it would be on a platform like GitHub, to guide you through this critical refactor.

***

### **Issue: Architectural Refactor - Replace Singletons and Globals with Dependency Injection**

**Labels:** `type: refactor`, `priority: critical`, `area: core-architecture`

#### **Problem Statement**

The current architecture, while largely modular, relies on singletons and global variables for accessing core services like the `SignalHandler`, `ModuleService`, and the `DebugUIServer` instance. This introduces global state and hidden dependencies, which has several critical negative impacts:

1.  **Untestability:** Core components like `MaestroCatAgent` and `MaestroCatLauncher` cannot be unit-tested in isolation because they fetch their dependencies from a global context. We cannot mock `get_signal_handler()` without complex patching that brittle.
2.  **Hidden Dependencies:** A component's reliance on a global service is not declared in its constructor or public interface. This makes the codebase difficult to reason about, as it's not clear what a class needs to function correctly.
3.  **Inflexibility:** We are locked into a single, global instance of these services. This prevents future scenarios like running multiple agent instances with different configurations within the same process.
4.  **Race Conditions & Unpredictable State:** Global state can be modified by any part of the application at any time, leading to unpredictable behavior, especially in a highly concurrent `asyncio` environment.

#### **Affected Components**

This issue is primarily centered around three key areas:

1.  **`SignalHandler` Singleton:**
    *   **File:** `core/platform/signal_handler.py`
    *   **Mechanism:** The `_signal_handler_instance = SignalHandler()` creates a module-level instance. The `get_signal_handler()` function acts as a global accessor.

2.  **`ModuleService` Singleton (Future-proofing):**
    *   **File:** `core/services/module_service.py`
    *   **Mechanism:** The `_instance` class variable and `get_instance()` class method implement the Singleton pattern. This service is not yet fully integrated, but fixing the pattern now is crucial.

3.  **`DebugUIServer` Global Instance:**
    *   **File:** `core/apps/debug_ui.py`
    *   **Mechanism:** A global variable `debug_server = None` is defined at the module level. The `DebugUIServer.start()` method then assigns `self` to this global variable. The FastAPI route handlers (`@app.get("/")`, `@app.websocket("/ws")`) then directly access this global `debug_server` variable. This is a very fragile coupling.

#### **Proposed Solution: The Composition Root**

We will refactor the system to use Dependency Injection (DI). The application's main entry point, the `main()` function in `maestrocat.py`, will become the **Composition Root**. This is the *single place* where top-level components are instantiated and wired together.

**Step-by-Step Plan:**

1.  **Refactor `SignalHandler`:**
    *   Remove the `_signal_handler_instance` global variable.
    *   Remove the `get_signal_handler()` global accessor function.
    *   The `SignalHandler` class itself is fine, it just needs to be instantiated normally.

2.  **Refactor `DebugUIServer` and FastAPI App:**
    *   Remove the `debug_server = None` global variable in `core/apps/debug_ui.py`.
    *   The FastAPI `app` instance should not be a global. It should be created by a function that accepts the `DebugUIServer` instance as a dependency. This allows the routes to have access to the server instance without a global variable.

3.  **Instantiate Dependencies in `maestrocat.py`:**
    *   In the `main()` function, create a single instance of `SignalHandler`.
    *   The `MaestroCatLauncher` will be responsible for creating the `MaestroCatAgent` and the `DebugUIServer`.

4.  **Inject Dependencies Down the Chain:**
    *   Modify the `__init__` method of `MaestroCatLauncher` to accept the `signal_handler` as an argument.
    *   Modify the `__init__` method of `MaestroCatAgent` to accept the `signal_handler` and `event_emitter` (which it already creates, but should be more explicit).
    *   The `MaestroCatAgent` will create the `DebugUIServer` instance. It will then create the FastAPI `app` using the factory function from step 2, passing the `DebugUIServer` instance to it.

---

#### **Code Implementation Guide (Before & After)**

**1. `core/platform/signal_handler.py`**

*   **BEFORE:**
    ```python
    # ...
    class SignalHandler:
        _instance = None
        # ...

    _signal_handler_instance = SignalHandler()

    def get_signal_handler() -> SignalHandler:
        return _signal_handler_instance
    ```

*   **AFTER:**
    ```python
    # ...
    class SignalHandler:
        # Remove the singleton logic (_instance, __new__)
        def __init__(self):
            self.agent = None
            self.loop = None
            self.shutdown_future = None
            self.shutting_down = False
        # ... rest of the class is fine

    # REMOVE the global instance and get_signal_handler() function
    ```

**2. `core/apps/debug_ui.py`**

*   **BEFORE:**
    ```python
    # ...
    app = FastAPI(title="MaestroCat Debug UI")
    # ...
    debug_server = None # GLOBAL VARIABLE

    @app.get("/")
    async def root():
        # Accesses global debug_server
        if os.path.exists(ui_dir) and debug_server:
            # ...
    
    class DebugUIServer:
        # ...
        async def start(self):
            global debug_server
            debug_server = self # ASSIGNS TO GLOBAL
            # ...
    ```

*   **AFTER (Proposed):**
    ```python
    # ...
    # REMOVE global app and debug_server variables

    def create_debug_app(debug_server_instance: "DebugUIServer") -> FastAPI:
        app = FastAPI(title="MaestroCat Debug UI")
        # Mount static files...

        @app.get("/")
        async def root():
            # Now has access via closure
            if os.path.exists(ui_dir) and debug_server_instance:
                # ...

        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            # Pass the instance to the connection manager or use it directly
            await manager.connect(websocket, debug_server_instance)

        # ... define all other routes inside this factory function ...
        return app
    
    class DebugUIServer:
        # ...
        async def start(self):
            # The start method NO LONGER assigns to a global.
            # It just runs the server.
            app = create_debug_app(self) # Create the app with self
            config = uvicorn.Config(
                app,
                host="0.0.0.0",
                port=self.port,
                log_level="info"
            )
            server = uvicorn.Server(config)
            await server.serve()
    ```

**3. `maestrocat.py` (The Composition Root)**

*   **BEFORE:**
    ```python
    # ...
    from core.platform.signal_handler import get_signal_handler, setup_signal_handlers

    class MaestroCatLauncher:
        def __init__(self):
            self.agent = None
            self.platform_info = None
            self.signal_handler = get_signal_handler() # Fetches global
    # ...
    def main():
        # ...
        launcher = MaestroCatLauncher()
        # ...
        signal_handler = get_signal_handler()
        signal_handler.register_loop(loop, shutdown_future)
        setup_signal_handlers()
    ```

*   **AFTER (Proposed):**
    ```python
    # ...
    from core.platform.signal_handler import SignalHandler, setup_signal_handlers # Import class directly

    class MaestroCatLauncher:
        def __init__(self, signal_handler: SignalHandler): # INJECT dependency
            self.agent = None
            self.platform_info = None
            self.signal_handler = signal_handler # USE injected dependency
    # ...
    def main():
        # ...
        # === COMPOSITION ROOT ===
        signal_handler = SignalHandler()
        launcher = MaestroCatLauncher(signal_handler=signal_handler)
        # ========================
        # ...
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        shutdown_future = loop.create_future()

        # Register loop with the handler instance
        signal_handler.register_loop(loop, shutdown_future)

        # Pass the handler instance to setup_signal_handlers
        setup_signal_handlers(signal_handler)
    ```    *(Note: `setup_signal_handlers` will also need to be modified to accept the `signal_handler` instance).*

#### **Acceptance Criteria**

-   [ ] The `get_signal_handler()` function and its global instance are removed from `core/platform/signal_handler.py`.
-   [ ] The `get_instance()` class method and its global instance are removed from `core/services/module_service.py`.
-   [ ] The global `debug_server` variable is removed from `core/apps/debug_ui.py`.
-   [ ] The `main()` function in `maestrocat.py` is the only place where `SignalHandler` is instantiated.
-   [ ] `MaestroCatLauncher` and `MaestroCatAgent` receive their dependencies (like `SignalHandler`) through their `__init__` constructors.
-   [ ] The FastAPI app for the debug UI is created via a factory function that receives the `DebugUIServer` instance, ensuring route handlers have access to it without a global variable.
-   [ ] The application runs end-to-end with `python maestrocat.py` and all features (voice agent, debug UI) are fully functional.
-   [ ] (Bonus) A basic unit test can be written for `MaestroCatLauncher` that passes in a mocked `SignalHandler`, proving the testability improvement.