import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageOps
import os
import numpy as np
import threading # Added for threading
# import traceback # Useful for debugging threaded errors

# For drag and drop, you might need to install TkinterDnD2: pip install tkinterdnd2
# If TkinterDnD2 is not available, the drag-and-drop functionality will be gracefully skipped.
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_SUPPORT = True
except ImportError:
    DND_SUPPORT = False

# --- Constants ---
APP_TITLE = "Image Combiner"
WINDOW_WIDTH = 500
WINDOW_HEIGHT = 650 # Increased height for better spacing
BG_COLOR = "#f0f0f0"
PRIMARY_COLOR = "#007AFF"
PRIMARY_FOREGROUND = "#FFFFFF"
TEXT_COLOR = "#333333"
BORDER_RADIUS_BUTTON = 10
DEFAULT_DPI = 300

PAPER_SIZES = {
    "8.5 x 13 inches": (int(8.5 * DEFAULT_DPI), int(13 * DEFAULT_DPI)),
    "8.5 x 14 inches": (int(8.5 * DEFAULT_DPI), int(14 * DEFAULT_DPI)),
}
OUTPUT_FORMATS = ["PDF", "PNG", "JPG"]

# --- Image Processing Functions ---

def find_best_overlap_height(img1_arr, img2_arr, search_proportion=0.95, step=1, sad_threshold=20):
    """
    Finds the height of the best vertical overlap between bottom of img1 and top of img2.
    Returns the height of this overlap (best_oh).
    """
    h1, w1, nc1 = img1_arr.shape
    h2, w2, nc2 = img2_arr.shape
    
    if nc1 != nc2:
        pass # Assuming 3 channels after RGB conversion
    num_channels = nc1 if nc1 > 0 else 1

    common_width = min(w1, w2)
    if common_width == 0:
        return 0

    max_overlap_physically_possible = min(h1, h2)
    if max_overlap_physically_possible < step :
        return 0

    search_range_max_h = int(max_overlap_physically_possible * search_proportion)
    search_range_max_h = max(step, search_range_max_h)
    search_range_max_h = min(search_range_max_h, max_overlap_physically_possible)

    min_norm_sad = float('inf')
    best_oh = 0

    for oh in range(step, search_range_max_h + 1, step):
        if oh == 0: continue

        strip1 = img1_arr[h1 - oh : h1, :common_width]
        strip2 = img2_arr[0 : oh, :common_width]

        if strip1.shape != strip2.shape:
            continue

        denominator = oh * common_width * num_channels
        if denominator == 0:
            continue

        sad = np.sum(np.abs(strip1.astype(np.float32) - strip2.astype(np.float32)))
        norm_sad = sad / denominator

        if norm_sad < min_norm_sad:
            min_norm_sad = norm_sad
            best_oh = oh

    min_significant_overlap_px = max(step, 5, int(0.01 * max_overlap_physically_possible))

    if best_oh < min_significant_overlap_px or min_norm_sad > sad_threshold:
        return 0
    
    return best_oh


def merge_images_vertically(image1_path, image2_path):
    """Merges two images vertically.
       Returns (merged_image_pil, None) on success, or (None, error_message_str) on failure.
    """
    try:
        img1_pil = Image.open(image1_path)
        img2_pil = Image.open(image2_path)
    except Exception as e:
        return None, f"Could not open images: {e}" # MODIFIED: Return error string

    if img1_pil.mode != 'RGB':
        img1_pil = img1_pil.convert('RGB')
    if img2_pil.mode != 'RGB':
        img2_pil = img2_pil.convert('RGB')

    img1_arr = np.array(img1_pil)
    img2_arr = np.array(img2_pil)

    h1, w1, _ = img1_arr.shape
    h2, w2, _ = img2_arr.shape

    overlap_h = find_best_overlap_height(img1_arr, img2_arr, 
                                         search_proportion=0.95,
                                         step=1,
                                         sad_threshold=25)

    top_part_pil = img1_pil

    if overlap_h > 0:
        crop_y_start_img2 = min(overlap_h, h2)
        bottom_part_pil = img2_pil.crop((0, crop_y_start_img2, w2, h2))
        if bottom_part_pil.height == 0:
            return img1_pil, None # Image 2 fully overlapped or too short
    else:
        bottom_part_pil = img2_pil

    if top_part_pil.height == 0 and bottom_part_pil.height == 0:
        return None, "Both image parts are empty after processing." # MODIFIED: Return error string
    elif top_part_pil.height == 0:
        return bottom_part_pil, None # Should ideally not happen if img1 is always top_part_pil
    elif bottom_part_pil.height == 0:
        return top_part_pil, None

    final_width = max(top_part_pil.width, bottom_part_pil.width)
    
    if top_part_pil.width < final_width:
        padded_top = Image.new(top_part_pil.mode, (final_width, top_part_pil.height), (255, 255, 255))
        paste_x = (final_width - top_part_pil.width) // 2
        padded_top.paste(top_part_pil, (paste_x, 0))
        top_part_pil = padded_top
    
    if bottom_part_pil.width < final_width:
        padded_bottom = Image.new(bottom_part_pil.mode, (final_width, bottom_part_pil.height), (255, 255, 255))
        paste_x = (final_width - bottom_part_pil.width) // 2
        padded_bottom.paste(bottom_part_pil, (paste_x, 0))
        bottom_part_pil = padded_bottom

    merged_height = top_part_pil.height + bottom_part_pil.height
    merged_image = Image.new(img1_pil.mode, (final_width, merged_height), (255, 255, 255))
    
    merged_image.paste(top_part_pil, (0, 0))
    merged_image.paste(bottom_part_pil, (0, top_part_pil.height))

    return merged_image, None # MODIFIED: Return tuple

def resize_image_to_spec(image, target_width_px, target_height_px):
    """Resizes image to fit within target_width_px and target_height_px, maintaining aspect ratio by padding."""
    original_width, original_height = image.size
    aspect_ratio = original_width / original_height

    if original_width / target_width_px > original_height / target_height_px:
        new_width = target_width_px
        new_height = int(new_width / aspect_ratio)
    else:
        new_height = target_height_px
        new_width = int(new_height * aspect_ratio)

    resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    final_image = Image.new(image.mode if image.mode != 'P' else 'RGB',
                            (target_width_px, target_height_px),
                            (255, 255, 255))
    
    paste_x = (target_width_px - new_width) // 2
    paste_y = (target_height_px - new_height) // 2
    final_image.paste(resized_image, (paste_x, paste_y))
    
    return final_image

# --- GUI Class ---
class ImageCombinerApp:
    def __init__(self, root):
        self.root = root
        # DND setup logic (remains the same)
        if DND_SUPPORT and isinstance(root, TkinterDnD.Tk):
             pass
        elif DND_SUPPORT:
            # This path implies DND_SUPPORT is true, but root is not TkinterDnD.Tk
            # The __main__ block should handle creating the correct root type.
            pass
        
        self.root.title(APP_TITLE)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.configure(bg=BG_COLOR)
        self.root.resizable(False, False)

        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("TFrame", background=BG_COLOR)
        self.style.configure("TLabel", background=BG_COLOR, foreground=TEXT_COLOR, padding=5, font=('Helvetica', 10))
        self.style.configure("TButton", foreground=PRIMARY_FOREGROUND, background=PRIMARY_COLOR, font=('Helvetica', 11, 'bold'), padding=(10, 8), relief="flat", borderwidth=0)
        self.style.map("TButton", background=[('active', '#0056b3')], relief=[('pressed', 'sunken'), ('!pressed', 'flat')])
        self.style.configure("Modern.TFrame", background="#ffffff", relief="solid", borderwidth=1, bordercolor="#cccccc")
        self.style.configure("TMenubutton", background="#ffffff", foreground=TEXT_COLOR, font=('Helvetica', 10), padding=6, relief="flat", arrowcolor=PRIMARY_COLOR)

        self.source_file1 = tk.StringVar()
        self.source_file2 = tk.StringVar()
        self.output_size_var = tk.StringVar(value=list(PAPER_SIZES.keys())[0])
        self.output_format_var = tk.StringVar(value=OUTPUT_FORMATS[0])

        # --- Attributes for processing state and UI elements ---
        self.process_button = None
        self.loading_frame = None
        self.progress_bar = None
        self.loading_label = None
        self.action_frame = None # To hold either button or loading indicator
        self.is_processing = False

        self._create_widgets()

    def _create_widgets(self):
        main_frame = ttk.Frame(self.root, padding=(20, 10), style="TFrame")
        main_frame.pack(expand=True, fill=tk.BOTH)

        title_label = ttk.Label(main_frame, text=APP_TITLE, font=('Helvetica', 18, 'bold'), foreground=PRIMARY_COLOR)
        title_label.pack(pady=(0, 20))

        ttk.Label(main_frame, text="Source Image 1 (Top)").pack(anchor='w', padx=10)
        self._create_file_input(main_frame, self.source_file1, 1).pack(fill=tk.X, padx=10, pady=(0,10))

        ttk.Label(main_frame, text="Source Image 2 (Bottom)").pack(anchor='w', padx=10)
        self._create_file_input(main_frame, self.source_file2, 2).pack(fill=tk.X, padx=10, pady=(0,20))

        options_frame = ttk.Frame(main_frame, style="TFrame")
        options_frame.pack(fill=tk.X, padx=10, pady=10)
        options_frame.columnconfigure(0, weight=1)
        options_frame.columnconfigure(1, weight=1)

        ttk.Label(options_frame, text="Output Paper Size:").grid(row=0, column=0, sticky='w', pady=(0,5))
        size_menu = ttk.OptionMenu(options_frame, self.output_size_var, self.output_size_var.get(), *PAPER_SIZES.keys())
        size_menu.grid(row=1, column=0, sticky='ew', padx=(0,5))
        self._style_option_menu(size_menu)

        ttk.Label(options_frame, text="Output Format:").grid(row=0, column=1, sticky='w', pady=(0,5))
        format_menu = ttk.OptionMenu(options_frame, self.output_format_var, self.output_format_var.get(), *OUTPUT_FORMATS)
        format_menu.grid(row=1, column=1, sticky='ew', padx=(5,0))
        self._style_option_menu(format_menu)
        
        # --- MODIFIED: Frame for button or loading indicator ---
        self.action_frame = ttk.Frame(main_frame, style="TFrame")
        self.action_frame.pack(pady=(30, 10))

        self.process_button = ttk.Button(self.action_frame, text="Process & Save", command=self.start_processing_task, style="TButton")
        self.process_button.pack(ipadx=20, ipady=5)

        # Loading indicator (initially hidden, packed into action_frame when needed)
        self.loading_frame = ttk.Frame(self.action_frame, style="TFrame")
        # self.loading_frame is not packed initially

        self.progress_bar = ttk.Progressbar(self.loading_frame, mode='indeterminate', length=150)
        self.progress_bar.pack(pady=(0, 5)) # Pack progress bar at the top
        self.loading_label = ttk.Label(self.loading_frame, text="Processing...", font=('Helvetica', 10))
        self.loading_label.pack(pady=(5, 0)) # Pack label below the progress bar
        # --- END MODIFICATION ---

        ttk.Frame(main_frame, height=10, style="TFrame").pack()


    def _create_file_input(self, parent, string_var, input_id):
        frame = ttk.Frame(parent, style="Modern.TFrame")
        entry = ttk.Label(frame, textvariable=string_var, background="#ffffff", foreground="#555555", font=('Helvetica', 9), relief="flat", width=40)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8,0), pady=5)
        string_var.set("Click 'Browse' or drag & drop file")

        browse_button = ttk.Button(frame, text="Browse", command=lambda sv=string_var: self._browse_file(sv), style="TButton", width=8)
        browse_button.pack(side=tk.RIGHT, padx=(0,5), pady=5)

        if DND_SUPPORT:
            def drop_enter(event):
                event.widget.focus_force()
                return event.action
            def drop_handler(event, sv=string_var):
                if event.data:
                    files = self.root.tk.splitlist(event.data)
                    if files:
                        sv.set(files[0])
                return event.action
            frame.drop_target_register(DND_FILES)
            frame.dnd_bind('<<DropEnter>>', drop_enter)
            frame.dnd_bind('<<Drop>>', drop_handler)
            entry.drop_target_register(DND_FILES)
            entry.dnd_bind('<<DropEnter>>', drop_enter)
            entry.dnd_bind('<<Drop>>', drop_handler)
        return frame
        
    def _style_option_menu(self, opt_menu):
        pass 

    def _browse_file(self, string_var):
        file_path = filedialog.askopenfilename(
            title="Select Image File",
            filetypes=(("Image files", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff"), ("All files", "*.*"))
        )
        if file_path:
            string_var.set(file_path)

    def _show_toast(self, title, message, duration=3000):
        toast = tk.Toplevel(self.root)
        toast.wm_overrideredirect(True)
        root_x, root_y = self.root.winfo_x(), self.root.winfo_y()
        root_width, root_height = self.root.winfo_width(), self.root.winfo_height()
        label = tk.Label(toast, text=message, bg="#333", fg="white", relief="solid", borderwidth=1, font=("Helvetica", 10), padx=10, pady=8)
        label.pack()
        toast.update_idletasks()
        toast_width, toast_height = label.winfo_width(), label.winfo_height()
        x = root_x + (root_width // 2) - (toast_width // 2)
        y = root_y + root_height - toast_height - 30
        toast.wm_geometry(f"+{x}+{y}")
        toast.wm_attributes("-topmost", True)
        toast.after(duration, toast.destroy)

    # --- MODIFIED: Processing Logic with Threading ---
    def start_processing_task(self):
        if self.is_processing:
            messagebox.showwarning("Busy", "Processing is already in progress.")
            return

        f1_path = self.source_file1.get()
        f2_path = self.source_file2.get()

        if not (os.path.exists(f1_path) and os.path.exists(f2_path)):
            messagebox.showerror("Error", "Please select two valid image files.")
            return

        self.is_processing = True
        self.process_button.pack_forget()  # Hide button
        self.loading_frame.pack()          # Show loading frame
        self.progress_bar.start(10)        # Start progress bar animation

        # Get values from Tkinter vars here, to pass to thread, ensuring main thread access
        target_size_name = self.output_size_var.get()
        output_format = self.output_format_var.get()

        thread = threading.Thread(target=self._background_process_and_save, 
                                  args=(f1_path, f2_path, target_size_name, output_format))
        thread.daemon = True # Allow main program to exit even if thread is running
        thread.start()

    def _background_process_and_save(self, f1_path, f2_path, target_size_name, output_format_str):
        # This runs in a worker thread
        try:
            merged_image, error = merge_images_vertically(f1_path, f2_path)
            if error:
                self.root.after(0, self._processing_finished, None, error, "background")
                return
            if merged_image is None: # Safeguard
                self.root.after(0, self._processing_finished, None, "Merging failed: Unknown reason.", "background")
                return

            target_w_px, target_h_px = PAPER_SIZES[target_size_name]
            final_image = resize_image_to_spec(merged_image, target_w_px, target_h_px)

            # Schedule save dialog and actual saving to run in the main thread
            self.root.after(0, self._prompt_save_and_finish, final_image, target_size_name, output_format_str)

        except Exception as e:
            # Catch any other unexpected errors during background processing
            # traceback.print_exc() # For debugging
            error_message = f"Error during background processing: {e}"
            self.root.after(0, self._processing_finished, None, error_message, "background")

    def _prompt_save_and_finish(self, final_image, target_size_name, output_format_str):
        # This runs in the main thread (called by root.after)
        if final_image is None: # Should be caught earlier, but as a safeguard
            self._processing_finished(None, "Image processing resulted in no image.", "background") # or "save_dialog"
            return

        output_format = output_format_str.lower()
        initial_filename = f"merged_image_to_{target_size_name.replace(' ', '_')}.{output_format}"
        
        save_path = filedialog.asksaveasfilename(
            initialfile=initial_filename,
            defaultextension=f".{output_format}",
            filetypes=(
                (f"{output_format.upper()} files", f"*.{output_format}"),
                ("All files", "*.*")
            )
        )

        if not save_path:
            self._show_toast("Cancelled", "Save operation cancelled.", 2000)
            self._processing_finished(None, "Save operation cancelled.", "save_dialog")
            return

        try:
            if output_format == 'pdf':
                if final_image.mode == 'RGBA': final_image = final_image.convert('RGB')
                final_image.save(save_path, "PDF", resolution=DEFAULT_DPI)
            elif output_format == 'jpg':
                if final_image.mode == 'RGBA' or final_image.mode == 'P': final_image = final_image.convert('RGB')
                final_image.save(save_path, "JPEG", quality=95, dpi=(DEFAULT_DPI, DEFAULT_DPI))
            elif output_format == 'png':
                final_image.save(save_path, "PNG", dpi=(DEFAULT_DPI, DEFAULT_DPI))
            else:
                final_image.save(save_path) # Let Pillow infer
            
            self._show_toast("Success!", f"Image saved to:\n{os.path.basename(save_path)}", 3000)
            messagebox.showinfo("File Saved", f"The image has been saved successfully to:\n{save_path}")
            self._processing_finished(final_image, None, "save_dialog") # Success

        except Exception as e:
            error_message = f"Could not save image: {e}"
            messagebox.showerror("Save Error", error_message) # Show specific error here
            self._show_toast("Error", "Failed to save image.", 3000)
            self._processing_finished(None, error_message, "save_dialog")

    def _processing_finished(self, result_image_or_none, error_message_or_none, error_source):
        # This runs in the main thread (called by root.after)
        # error_source helps determine if a messagebox needs to be shown here or was handled already
        
        self.progress_bar.stop()
        self.loading_frame.pack_forget()   # Hide loading frame
        self.process_button.pack(ipadx=20, ipady=5) # Show button again
        self.is_processing = False

        if error_message_or_none and error_source == "background":
            # This error happened in the worker thread (e.g., merge, resize)
            # and _prompt_save_and_finish was never called or didn't handle this specific message.
            messagebox.showerror("Processing Error", error_message_or_none)
        # If error_source is "save_dialog", _prompt_save_and_finish handled its own popups.
        # If no error_message_or_none, it was a success, and _prompt_save_and_finish handled success popups.
    # --- END MODIFICATION ---


# --- Main Execution ---
if __name__ == "__main__":
    if DND_SUPPORT:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
        print("Note: TkinterDnD2 not found. Drag and drop functionality will be disabled.")
        print("You can install it with: pip install tkinterdnd2")
        
    app = ImageCombinerApp(root)
    root.mainloop()
