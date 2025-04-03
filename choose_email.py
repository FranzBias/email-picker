import customtkinter as ctk

# Set global appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Example email list – you can customize these
emails = [
    "email.address1@your.site",
    "email.address2@your.site",
    "your.name@example.com",
    "test.user@demo.net"
]

# Function triggered when user clicks the button
def copy_email():
    email = combo.get()
    if email:
        app.clipboard_clear()
        app.clipboard_append(email)
        app.update()

        # Change button appearance after copy
        button.configure(
            text="Email copied ✅",
            fg_color="#2ecc71",             # Green
            text_color="#ffffff",           # White
            font=("Arial", 14, "bold"),
            command=lambda: None            # Disable click
        )
        app.after(2000, app.destroy)
    else:
        button.configure(text="Please select an email!", fg_color="red")
        app.after(2000, lambda: button.configure(text="Copy email", fg_color=None))

app = ctk.CTk()
app.title("Choose an Email")
app.geometry("400x200+500+300")

label = ctk.CTkLabel(app, text="Select an email to copy to clipboard:")
label.pack(pady=10)

combo = ctk.CTkComboBox(app, values=emails, width=300)
combo.pack(pady=10)

button = ctk.CTkButton(app, text="Copy email", command=copy_email)
button.pack(pady=20)

app.mainloop()
