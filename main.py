import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageOps
import os
import numpy as np

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
BG_COLOR = "#f0f0f0"  # Light gray background
PRIMARY_COLOR = "#007AFF"  # A modern blue
PRIMARY_FOREGROUND = "#FFFFFF" # White text on blue buttons
TEXT_COLOR = "#333333"
BORDER_RADIUS_BUTTON = 10 # For custom buttons if we draw them; ttk styling is different
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
    search_proportion: Max proportion of the shorter image's height to search for overlap.
    step: Step size for iterating through possible overlap heights.
    sad_threshold: Maximum average Sum of Absolute Differences per pixel/channel to consider a match.
    """
    h1, w1, nc1 = img1_arr.shape
    h2, w2, nc2 = img2_arr.shape
    
    # This should be true after RGB conversion, but as a safeguard:
    if nc1 != nc2: 
        # print("Warning: Channel count mismatch between images. This might affect SAD calculation.")
        # Fallback or error, for now, assume they are compatible (e.g. 3 channels)
        pass
    num_channels = nc1 if nc1 > 0 else 1 # Avoid division by zero if nc is 0 for some reason

    common_width = min(w1, w2)
    if common_width == 0:
        return 0  # No overlap possible

    max_overlap_physically_possible = min(h1, h2)
    if max_overlap_physically_possible < step : # Must be able to take at least one step
        return 0

    # search_range_max_h is the maximum overlap height we will test.
    search_range_max_h = int(max_overlap_physically_possible * search_proportion)
    search_range_max_h = max(step, search_range_max_h) # Must be at least step size.
    search_range_max_h = min(search_range_max_h, max_overlap_physically_possible) # Cannot exceed physical possibility.

    min_norm_sad = float('inf')
    best_oh = 0  # Best overlap height found

    # Iterate through possible overlap heights 'oh'
    # Start from `step` and go up to `search_range_max_h`
    for oh in range(step, search_range_max_h + 1, step):
        if oh == 0: continue # Overlap height must be positive

        strip1 = img1_arr[h1 - oh : h1, :common_width]  # Bottom of img1
        strip2 = img2_arr[0 : oh, :common_width]       # Top of img2

        if strip1.shape != strip2.shape: # Should not happen with correct oh calculation
            # print(f"Shape mismatch: strip1 {strip1.shape}, strip2 {strip2.shape} for oh={oh}")
            continue

        # Ensure denominator for SAD normalization is not zero
        denominator = oh * common_width * num_channels
        if denominator == 0:
            continue

        sad = np.sum(np.abs(strip1.astype(np.float32) - strip2.astype(np.float32)))
        norm_sad = sad / denominator

        if norm_sad < min_norm_sad:
            min_norm_sad = norm_sad
            best_oh = oh

    # Heuristic: If the best found overlap's SAD is too high, it's not a good match.
    # Also, enforce a minimum significant overlap size.
    min_significant_overlap_px = max(step, 5, int(0.01 * max_overlap_physically_possible))

    # print(f"Overlap search: best_oh={best_oh}px, min_norm_sad={min_norm_sad:.2f} (threshold: {sad_threshold}), min_px_req: {min_significant_overlap_px}")

    if best_oh < min_significant_overlap_px or min_norm_sad > sad_threshold:
        # print(f"Overlap {best_oh}px (SAD: {min_norm_sad:.2f}) not good enough. SAD_thresh={sad_threshold}, Min_px={min_significant_overlap_px}. Defaulting to 0 overlap.")
        return 0  # Not a good enough overlap, treat as no overlap.
    
    # print(f"Found best overlap height: {best_oh}px, norm_sad={min_norm_sad:.2f}")
    return best_oh


def merge_images_vertically(image1_path, image2_path):
    """Merges two images vertically. Takes all of image1 and appends image2,
       trimming the top of image2 if a significant overlap is found."""
    try:
        img1_pil = Image.open(image1_path)
        img2_pil = Image.open(image2_path)
    except Exception as e:
        messagebox.showerror("Error", f"Could not open images: {e}")
        return None

    # Convert to RGB for consistent processing
    if img1_pil.mode != 'RGB':
        img1_pil = img1_pil.convert('RGB')
    if img2_pil.mode != 'RGB':
        img2_pil = img2_pil.convert('RGB')

    img1_arr = np.array(img1_pil)
    img2_arr = np.array(img2_pil)

    h1, w1, _ = img1_arr.shape
    h2, w2, _ = img2_arr.shape

    # Find the height of the overlap region.
    # For "90% match" scenarios, search_proportion should be high.
    # step=1 provides max accuracy but can be slower. Increase if needed.
    # sad_threshold=20 means average pixel difference < 20 (out of 255) is considered a match.
    # You might need to tune sad_threshold based on your scan quality.
    overlap_h = find_best_overlap_height(img1_arr, img2_arr, 
                                         search_proportion=0.95, # Search up to 95% of shorter image height for overlap
                                         step=1,                 # Check every possible overlap height
                                         sad_threshold=25)       # Allow slightly more difference

    top_part_pil = img1_pil # Use all of the first image

    if overlap_h > 0:
        # print(f"Significant overlap of {overlap_h}px found. Trimming top of image 2.")
        # Image 2 starts after the detected overlap
        crop_y_start_img2 = min(overlap_h, h2) # Ensure crop doesn't exceed img2 height
        bottom_part_pil = img2_pil.crop((0, crop_y_start_img2, w2, h2))

        if bottom_part_pil.height == 0: # Entire img2 was considered overlap or img2 was shorter than overlap
            # print("Image 2 is fully overlapped or too short; using only Image 1.")
            # Merged image is just image1, no need to do more.
            # Width adjustment might still be needed if we were to combine with a blank canvas,
            # but for now, just return img1_pil. Later, resize_to_spec will handle final sizing.
            return img1_pil 
    else:
        # print("No significant overlap found, or overlap quality too low. Appending Image 2 fully.")
        bottom_part_pil = img2_pil # Use all of the second image

    # --- Combine top_part_pil and bottom_part_pil ---

    # Ensure parts are not empty before proceeding
    if top_part_pil.height == 0 and bottom_part_pil.height == 0:
        messagebox.showwarning("Merge Warning", "Both image parts are empty after processing.")
        return Image.new('RGB', (100, 100), (255,255,255)) # Placeholder
    elif top_part_pil.height == 0: # Should not happen as top_part_pil is img1_pil
        return bottom_part_pil
    elif bottom_part_pil.height == 0: # Can happen if img2 was fully overlapped AND img1 is returned above.
                                      # This path means overlap_h was 0, but img2 was empty.
        return top_part_pil


    # Pad widths to match, centering the narrower image.
    final_width = max(top_part_pil.width, bottom_part_pil.width)
    
    # Pad top_part_pil if it's narrower
    if top_part_pil.width < final_width:
        padded_top = Image.new(top_part_pil.mode, (final_width, top_part_pil.height), (255, 255, 255))
        paste_x = (final_width - top_part_pil.width) // 2
        padded_top.paste(top_part_pil, (paste_x, 0))
        top_part_pil = padded_top
    
    # Pad bottom_part_pil if it's narrower
    if bottom_part_pil.width < final_width:
        padded_bottom = Image.new(bottom_part_pil.mode, (final_width, bottom_part_pil.height), (255, 255, 255))
        paste_x = (final_width - bottom_part_pil.width) // 2
        padded_bottom.paste(bottom_part_pil, (paste_x, 0))
        bottom_part_pil = padded_bottom

    merged_height = top_part_pil.height + bottom_part_pil.height
    merged_image = Image.new(img1_pil.mode, (final_width, merged_height), (255, 255, 255)) # Use mode of img1_pil
    
    merged_image.paste(top_part_pil, (0, 0))
    merged_image.paste(bottom_part_pil, (0, top_part_pil.height))

    return merged_image

def resize_image_to_spec(image, target_width_px, target_height_px):
    """Resizes image to fit within target_width_px and target_height_px, maintaining aspect ratio by padding."""
    original_width, original_height = image.size
    aspect_ratio = original_width / original_height

    # Calculate new dimensions to fit within target, maintaining aspect ratio
    if original_width / target_width_px > original_height / target_height_px:
        # Width is the limiting factor
        new_width = target_width_px
        new_height = int(new_width / aspect_ratio)
    else:
        # Height is the limiting factor
        new_height = target_height_px
        new_width = int(new_height * aspect_ratio)

    resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # Create a new image with the target dimensions and paste the resized image onto it (padding)
    # This ensures the output is exactly the target paper size.
    final_image = Image.new(image.mode if image.mode != 'P' else 'RGB',
                            (target_width_px, target_height_px),
                            (255, 255, 255)) # White background for padding
    
    paste_x = (target_width_px - new_width) // 2
    paste_y = (target_height_px - new_height) // 2
    final_image.paste(resized_image, (paste_x, paste_y))
    
    return final_image

# --- GUI Class ---
class ImageCombinerApp:
    def __init__(self, root):
        self.root = root
        if DND_SUPPORT and isinstance(root, TkinterDnD.Tk): # Check if root is DND enabled
             pass # TkinterDnD.Tk() handles its own initialization
        elif DND_SUPPORT: # If root is a normal tk.Tk, make it DND-aware
            self.root = TkinterDnD.Tk() # This creates a new root, so we'd need to manage that.
                                        # It's better to initialize root as TkinterDnD.Tk() from the start.
                                        # For this structure, we assume root is already the correct type if DND is used.
        
        self.root.title(APP_TITLE)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.configure(bg=BG_COLOR)
        self.root.resizable(False, False)

        # --- Style ---
        self.style = ttk.Style()
        self.style.theme_use('clam') # More modern base theme

        self.style.configure("TFrame", background=BG_COLOR) # Ensure frames match BG_COLOR
        self.style.configure("TLabel", background=BG_COLOR, foreground=TEXT_COLOR, padding=5, font=('Helvetica', 10))
        self.style.configure("TButton",
                             foreground=PRIMARY_FOREGROUND,
                             background=PRIMARY_COLOR,
                             font=('Helvetica', 11, 'bold'),
                             padding=(10, 8),
                             relief="flat",
                             borderwidth=0)
        self.style.map("TButton",
                       background=[('active', '#0056b3')], # Darker blue on hover/press
                       relief=[('pressed', 'sunken'), ('!pressed', 'flat')])

        # Custom style for "modern" entry-like frames
        self.style.configure("Modern.TFrame", background="#ffffff", relief="solid", borderwidth=1, bordercolor="#cccccc")
        
        self.style.configure("TMenubutton", background="#ffffff", foreground=TEXT_COLOR, font=('Helvetica', 10), padding=6, relief="flat", arrowcolor=PRIMARY_COLOR)


        # --- Variables ---
        self.source_file1 = tk.StringVar()
        self.source_file2 = tk.StringVar()
        self.output_size_var = tk.StringVar(value=list(PAPER_SIZES.keys())[0])
        self.output_format_var = tk.StringVar(value=OUTPUT_FORMATS[0])

        # --- UI Elements ---
        self._create_widgets()

    def _create_widgets(self):
        main_frame = ttk.Frame(self.root, padding=(20, 10), style="TFrame") # Main container
        main_frame.pack(expand=True, fill=tk.BOTH)
        main_frame.configure(style="TFrame") # Ensure BG_COLOR for main_frame as well

        # Title
        title_label = ttk.Label(main_frame, text=APP_TITLE, font=('Helvetica', 18, 'bold'), foreground=PRIMARY_COLOR)
        title_label.pack(pady=(0, 20))

        # Source File 1
        ttk.Label(main_frame, text="Source Image 1 (Top)").pack(anchor='w', padx=10)
        self._create_file_input(main_frame, self.source_file1, 1).pack(fill=tk.X, padx=10, pady=(0,10))

        # Source File 2
        ttk.Label(main_frame, text="Source Image 2 (Bottom)").pack(anchor='w', padx=10)
        self._create_file_input(main_frame, self.source_file2, 2).pack(fill=tk.X, padx=10, pady=(0,20))

        # Output Options Frame
        options_frame = ttk.Frame(main_frame, style="TFrame")
        options_frame.pack(fill=tk.X, padx=10, pady=10)
        options_frame.columnconfigure(0, weight=1)
        options_frame.columnconfigure(1, weight=1)

        # Output Paper Size
        ttk.Label(options_frame, text="Output Paper Size:").grid(row=0, column=0, sticky='w', pady=(0,5))
        size_menu = ttk.OptionMenu(options_frame, self.output_size_var, self.output_size_var.get(), *PAPER_SIZES.keys())
        size_menu.grid(row=1, column=0, sticky='ew', padx=(0,5))
        self._style_option_menu(size_menu)


        # Output Format
        ttk.Label(options_frame, text="Output Format:").grid(row=0, column=1, sticky='w', pady=(0,5))
        format_menu = ttk.OptionMenu(options_frame, self.output_format_var, self.output_format_var.get(), *OUTPUT_FORMATS)
        format_menu.grid(row=1, column=1, sticky='ew', padx=(5,0))
        self._style_option_menu(format_menu)
        
        # Process Button
        process_button = ttk.Button(main_frame, text="Process & Save", command=self.process_images, style="TButton")
        process_button.pack(pady=(30, 10), ipadx=20, ipady=5) # ipadx, ipady for internal padding

        # Footer for a bit of space
        ttk.Frame(main_frame, height=10, style="TFrame").pack()


    def _create_file_input(self, parent, string_var, input_id):
        """Creates a 'modern' looking file input composite widget."""
        frame = ttk.Frame(parent, style="Modern.TFrame") # Use the custom styled frame

        entry = ttk.Label(frame, textvariable=string_var, background="#ffffff", foreground="#555555", font=('Helvetica', 9), relief="flat", width=40)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8,0), pady=5) # Pad inside the frame
        string_var.set("Click 'Browse' or drag & drop file")


        browse_button = ttk.Button(frame, text="Browse",
                                   command=lambda sv=string_var: self._browse_file(sv),
                                   style="TButton", width=8) # Smaller button
        browse_button.pack(side=tk.RIGHT, padx=(0,5), pady=5)

        if DND_SUPPORT:
            def drop_enter(event):
                event.widget.focus_force() # Indicate receptiveness
                return event.action

            def drop_handler(event, sv=string_var):
                if event.data:
                    files = self.root.tk.splitlist(event.data)
                    if files:
                        sv.set(files[0]) # Take the first dropped file
                return event.action

            # Apply DND to the entry label (or frame for wider area)
            # Using the frame makes the drop target larger
            frame.drop_target_register(DND_FILES)
            frame.dnd_bind('<<DropEnter>>', drop_enter)
            frame.dnd_bind('<<Drop>>', drop_handler)
            # Also make the label a drop target to show text change immediately
            entry.drop_target_register(DND_FILES)
            entry.dnd_bind('<<DropEnter>>', drop_enter)
            entry.dnd_bind('<<Drop>>', drop_handler)

        return frame
        
    def _style_option_menu(self, opt_menu):
        """Apply some styling to OptionMenu if possible."""
        # opt_menu['menu'].configure(font=('Helvetica', 10), background="#ffffff", relief="flat", activebackground=PRIMARY_COLOR, activeforeground=PRIMARY_FOREGROUND)
        # opt_menu.config(style="TMenubutton") # Using ttk.OptionMenu is generally better
        pass # ttk.OptionMenu is harder to style deeply without complex Tkinter work.
             # The default ttk style should be acceptable.

    def _browse_file(self, string_var):
        file_path = filedialog.askopenfilename(
            title="Select Image File",
            filetypes=(("Image files", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff"), ("All files", "*.*"))
        )
        if file_path:
            string_var.set(file_path)

    def _show_toast(self, title, message, duration=3000):
        toast = tk.Toplevel(self.root)
        toast.wm_overrideredirect(True) # No window decorations
        # Position it bottom center of the main window
        root_x = self.root.winfo_x()
        root_y = self.root.winfo_y()
        root_width = self.root.winfo_width()
        root_height = self.root.winfo_height()

        label = tk.Label(toast, text=message, bg="#333", fg="white", relief="solid", borderwidth=1, font=("Helvetica", 10), padx=10, pady=8)
        label.pack()
        
        toast.update_idletasks() # Ensure dimensions are calculated
        toast_width = label.winfo_width()
        toast_height = label.winfo_height()
        
        x = root_x + (root_width // 2) - (toast_width // 2)
        y = root_y + root_height - toast_height - 30 # 30px from bottom
        toast.wm_geometry(f"+{x}+{y}")
        toast.wm_attributes("-topmost", True)
        toast.after(duration, toast.destroy)


    def process_images(self):
        f1_path = self.source_file1.get()
        f2_path = self.source_file2.get()
        
        if not (os.path.exists(f1_path) and os.path.exists(f2_path)):
            messagebox.showerror("Error", "Please select two valid image files.")
            return

        # 1. Merge images
        merged_image = merge_images_vertically(f1_path, f2_path)
        if merged_image is None:
            # Error handled in merge_images_vertically
            return

        # 2. Get target dimensions
        target_size_name = self.output_size_var.get()
        target_w_px, target_h_px = PAPER_SIZES[target_size_name]

        # 3. Resize merged image
        final_image = resize_image_to_spec(merged_image, target_w_px, target_h_px)

        # 4. Save the image
        output_format = self.output_format_var.get().lower()
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
            return

        try:
            if output_format == 'pdf':
                # Ensure image is RGB for PDF saving if not already
                if final_image.mode == 'RGBA':
                     final_image = final_image.convert('RGB')
                final_image.save(save_path, "PDF", resolution=DEFAULT_DPI)
            elif output_format == 'jpg':
                if final_image.mode == 'RGBA' or final_image.mode == 'P': # JPG doesn't support alpha
                     final_image = final_image.convert('RGB')
                final_image.save(save_path, "JPEG", quality=95, dpi=(DEFAULT_DPI, DEFAULT_DPI))
            elif output_format == 'png':
                final_image.save(save_path, "PNG", dpi=(DEFAULT_DPI, DEFAULT_DPI))
            else:
                final_image.save(save_path) # Let Pillow infer
            
            self._show_toast("Success!", f"Image saved to:\n{os.path.basename(save_path)}", 3000)
            # Open file location pop-up (not directly possible, but can show path)
            messagebox.showinfo("File Saved", f"The image has been saved successfully to:\n{save_path}")

        except Exception as e:
            messagebox.showerror("Save Error", f"Could not save image: {e}")
            self._show_toast("Error", "Failed to save image.", 3000)

# --- Main Execution ---
if __name__ == "__main__":
    if DND_SUPPORT:
        root = TkinterDnD.Tk() # Use TkinterDnD Tk object if available
    else:
        root = tk.Tk()
        print("Note: TkinterDnD2 not found. Drag and drop functionality will be disabled.")
        print("You can install it with: pip install tkinterdnd2")
        
    app = ImageCombinerApp(root)
    root.mainloop()
