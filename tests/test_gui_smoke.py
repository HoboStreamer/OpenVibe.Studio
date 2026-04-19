import tkinter as tk
import unittest

from openvibe_studio.app import TaskRunner


class GuiSmokeTestCase(unittest.TestCase):
    def test_task_runner_executes_callback(self):
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("Tkinter display unavailable")
            return
        root.withdraw()
        runner = TaskRunner(root)
        results = []

        def action():
            return "done"

        def callback(result):
            results.append(result)
            root.quit()

        runner.submit(action, callback)
        root.after(2000, root.quit)
        root.mainloop()
        self.assertEqual(results, ["done"])
        root.destroy()


if __name__ == "__main__":
    unittest.main()
