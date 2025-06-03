import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageOps
import os
import numpy as np
from concurrent.futures import ThreadPoolExecutor

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
WINDOW_HEIGHT = 650
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

# --- Optimized Image Processing Functions ---

def find_best_overlap_height_optimized(img1_arr, img2_arr, search_proportion=0.95, step=5, sad_threshold=20):
    """
    OPTIMIZED: Finds the height of the best vertical overlap between bottom of img1 and top of img2.
    Key optimizations:
    1. Increased default step size from 1 to 5 for faster search
    2. Use float32 arrays for faster computation
    3. Vectorized operations with NumPy
    4. Early termination on very good matches
    5. Reduced precision for initial search, then refine
    """
    h1, w1, nc1 = img1_arr.shape
    h2, w2, nc2 = img2_arr.shape
    
    if nc1 != nc2:
        pass  # Assuming 3 channels after RGB conversion
    num_channels = nc1 if nc1 > 0 else 1

    common_width = min(w1, w2)
    if common_width == 0:
        return 0

    max_overlap_physically_possible = min(h1, h2)
    if max_overlap_physically_possible < step:
        return 0

    search_range_max_h = int(max_overlap_physically_possible * search_proportion)
    search_range_max_h = max(step, search_range_max_h)
    search_range_max_h = min(search_range_max_h, max_overlap_physically_possible)

    # Convert to float32 for faster computation
    img1_float = img1_arr.astype(np.float32)
    img2_float = img2_arr.astype(np.float32)

    min_norm_sad = float('inf')
    best_oh = 0
    
    # Coarse search with larger step
    coarse_step = max(step, 10)
    coarse_candidates = []
    
    for oh in range(coarse_step, search_range_max_h + 1, coarse_step):
        if oh == 0:
            continue

        strip1 = img1_float[h1 - oh : h1, :common_width]
        strip2 = img2_float[0 : oh, :common_width]

        if strip1.shape != strip2.shape:
            continue

        denominator = oh * common_width * num_channels
        if denominator == 0:
            continue

        # Vectorized SAD computation
        sad = np.sum(np.abs(strip1 - strip2))
        norm_sad = sad / denominator

        coarse_candidates.append((oh, norm_sad))
        
        if norm_sad < min_norm_sad:
            min_norm_sad = norm_sad
            best_oh = oh
            
        # Early termination for very good matches
        if norm_sad < sad_threshold * 0.5:
            break

    # Fine search around best coarse candidate
    if coarse_candidates and best_oh > 0:
        search_start = max(step, best_oh - coarse_step + 1)
        search_end = min(search_range_max_h, best_oh + coarse_step)
        
        for oh in range(search_start, search_end + 1, step):
            if oh == best_oh:  # Already computed
                continue
                
            strip1 = img1_float[h1 - oh : h1, :common_width]
            strip2 = img2_float[0 : oh, :common_width]

            if strip1.shape != strip2.shape:
                continue

            denominator = oh * common_width * num_channels
            if denominator == 0:
                continue

            sad = np.sum(np.abs(strip1 - strip2))
            norm_sad = sad / denominator

            if norm_sad < min_norm_sad:
                min_norm_sad = norm_sad
                best_oh = oh

    min_significant_overlap_px = max(step, 5, int(0.01 * max_overlap_physically_possible))

    if best_oh < min_significant_overlap_px or min_norm_sad > sad_threshold:
        return 0
    
    return best_oh


def load_and_preprocess_image(image_path, target_max_dimension=3000):
    """
    OPTIMIZED: Load and optionally downsample large images for faster processing.
    Only downsample for overlap detection, keep originals for final merge.
    """
    try:
        img_pil = Image.open(image_path)
        if img_pil.mode != 'RGB':
            img_pil = img_pil.convert('RGB')
        
        # Check if image is very large and downsample for processing
        max_dim = max(img_pil.width, img_pil.height)
        if max_dim > target_max_dimension:
            scale_factor = target_max_dimension / max_dim
            new_width = int(img_pil.width * scale_factor)
            new_height = int(img_pil.height * scale_factor)
            processed_img = img_pil.resize((new_width, new_height), Image.Resampling.LANCZOS)
            return img_pil, processed_img, scale_factor
        else:
            return img_pil, img_pil, 1.0
            
    except Exception as e:
        return None, None, 0.0


def merge_images_vertically_optimized(image1_path, image2_path):
    """
    OPTIMIZED: Merges two images vertically with performance improvements.
    """
    try:
        # Load original and processing versions
        img1_orig, img1_proc, scale1 = load_and_preprocess_image(image1_path)
        img2_orig, img2_proc, scale2 = load_and_preprocess_image(image2_path)
        
        if img1_orig is None or img2_orig is None:
            return None, "Could not open one or both images"
            
    except Exception as e:
        return None, f"Could not open images: {e}"

    # Use processed (potentially downsampled) images for overlap detection
    img1_arr = np.array(img1_proc)
    img2_arr = np.array(img2_proc)

    h1, w1, _ = img1_arr.shape
    h2, w2, _ = img2_arr.shape

    # Find overlap using processed images
    overlap_h_proc = find_best_overlap_height_optimized(
        img1_arr, img2_arr, 
        search_proportion=0.95,
        step=5,  # Increased step size
        sad_threshold=25
    )

    # Scale overlap back to original image dimensions
    overlap_h = int(overlap_h_proc / min(scale1, scale2)) if overlap_h_proc > 0 else 0

    # Use original images for final merge
    top_part_pil = img1_orig

    if overlap_h > 0:
        crop_y_start_img2 = min(overlap_h, img2_orig.height)
        bottom_part_pil = img2_orig.crop((0, crop_y_start_img2, img2_orig.width, img2_orig.height))
        if bottom_part_pil.height == 0:
            return img1_orig, None
    else:
        bottom_part_pil = img2_orig

    if top_part_pil.height == 0 and bottom_part_pil.height == 0:
        return None, "Both image parts are empty after processing."
    elif top_part_pil.height == 0:
        return bottom_part_pil, None
    elif bottom_part_pil.height == 0:
        return top_part_pil, None

    final_width = max(top_part_pil.width, bottom_part_pil.width)
    
    # Optimize padding operations
    if top_part_pil.width < final_width:
        padded_top = Image.new('RGB', (final_width, top_part_pil.height), (255, 255, 255))
        paste_x = (final_width - top_part_pil.width) // 2
        padded_top.paste(top_part_pil, (paste_x, 0))
        top_part_pil = padded_top
    
    if bottom_part_pil.width < final_width:
        padded_bottom = Image.new('RGB', (final_width, bottom_part_pil.height), (255, 255, 255))
        paste_x = (final_width - bottom_part_pil.width) // 2
        padded_bottom.paste(bottom_part_pil, (paste_x, 0))
        bottom_part_pil = padded_bottom

    merged_height = top_part_pil.height + bottom_part_pil.height
    merged_image = Image.new('RGB', (final_width, merged_height), (255, 255, 255))
    
    merged_image.paste(top_part_pil, (0, 0))
    merged_image.paste(bottom_part_pil, (0, top_part_pil.height))

    return merged_image, None


def resize_image_to_spec_optimized(image, target_width_px, target_height_px):
    """
    OPTIMIZED: Resizes image with better resampling algorithm selection.
    """
    original_width, original_height = image.size
    aspect_ratio = original_width / original_height

    if original_width / target_width_px > original_height / target_height_px:
        new_width = target_width_px
        new_height = int(new_width / aspect_ratio)
    else:
        new_height = target_height_px
        new_width = int(new_height * aspect_ratio)

    # Choose resampling method based on scale factor
    scale_factor = min(new_width / original_width, new_height / original_height)
    if scale_factor < 0.5:
        # For significant downscaling, use LANCZOS
        resampling = Image.Resampling.LANCZOS
    else:
        # For upscaling or minor downscaling, use BICUBIC (faster)
        resampling = Image.Resampling.BICUBIC

    resized_image = image.resize((new_width, new_height), resampling)

    final_image = Image.new('RGB', (target_width_px, target_height_px), (255, 255, 255))
    
    paste_x = (target_width_px - new_width) // 2
    paste_y = (target_height_px - new_height) // 2
    final_image.paste(resized_image, (paste_x, paste_y))
    
    return final_image


# --- GUI Class (with minimal changes) ---
class ImageCombinerApp:
    def __init__(self, root):
        self.root = root
        # DND setup logic (remains the same)
        if DND_SUPPORT and isinstance(root, TkinterDnD.Tk):
             pass
        elif DND_SUPPORT:
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
        self.action_frame = None
        self.is_processing = False

        # Thread pool for background operations
        self.executor = ThreadPoolExecutor(max_workers=2)

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
        
        self.action_frame = ttk.Frame(main_frame, style="TFrame")
        self.action_frame.pack(pady=(30, 10))

        self.process_button = ttk.Button(self.action_frame, text="Process & Save", command=self.start_processing_task, style="TButton")
        self.process_button.pack(ipadx=20, ipady=5)

        self.loading_frame = ttk.Frame(self.action_frame, style="TFrame")
        self.progress_bar = ttk.Progressbar(self.loading_frame, mode='indeterminate', length=150)
        self.progress_bar.pack(pady=(0, 5))
        self.loading_label = ttk.Label(self.loading_frame, text="Processing...", font=('Helvetica', 10))
        self.loading_label.pack(pady=(5, 0))

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
        self.process_button.pack_forget()
        self.loading_frame.pack()
        self.progress_bar.start(10)

        target_size_name = self.output_size_var.get()
        output_format = self.output_format_var.get()

        # Submit to thread pool instead of creating raw thread
        future = self.executor.submit(self._background_process_and_save, 
                                     f1_path, f2_path, target_size_name, output_format)

    def _background_process_and_save(self, f1_path, f2_path, target_size_name, output_format_str):
        try:
            # Use optimized functions
            merged_image, error = merge_images_vertically_optimized(f1_path, f2_path)
            if error:
                self.root.after(0, self._processing_finished, None, error, "background")
                return
            if merged_image is None:
                self.root.after(0, self._processing_finished, None, "Merging failed: Unknown reason.", "background")
                return

            target_w_px, target_h_px = PAPER_SIZES[target_size_name]
            final_image = resize_image_to_spec_optimized(merged_image, target_w_px, target_h_px)

            self.root.after(0, self._prompt_save_and_finish, final_image, target_size_name, output_format_str)

        except Exception as e:
            error_message = f"Error during background processing: {e}"
            self.root.after(0, self._processing_finished, None, error_message, "background")

    def _prompt_save_and_finish(self, final_image, target_size_name, output_format_str):
        if final_image is None:
            self._processing_finished(None, "Image processing resulted in no image.", "background")
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
                final_image.save(save_path)
            
            self._show_toast("Success!", f"Image saved to:\n{os.path.basename(save_path)}", 3000)
            messagebox.showinfo("File Saved", f"The image has been saved successfully to:\n{save_path}")
            self._processing_finished(final_image, None, "save_dialog")

        except Exception as e:
            error_message = f"Could not save image: {e}"
            messagebox.showerror("Save Error", error_message)
            self._show_toast("Error", "Failed to save image.", 3000)
            self._processing_finished(None, error_message, "save_dialog")

    def _processing_finished(self, result_image_or_none, error_message_or_none, error_source):
        self.progress_bar.stop()
        self.loading_frame.pack_forget()
        self.process_button.pack(ipadx=20, ipady=5)
        self.is_processing = False

        if error_message_or_none and error_source == "background":
            messagebox.showerror("Processing Error", error_message_or_none)

    def __del__(self):
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)


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