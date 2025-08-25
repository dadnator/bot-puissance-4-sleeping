import os
import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
import sqlite3
from datetime import datetime
from keep_alive import keep_alive # Assume this is handled by your environment

token = os.environ['TOKEN_BOT_DISCORD']

# Rôles et salon du serveur
ID_CROUPIER = 1401471414262829066
ID_MEMBRE = 1366378672281620495
ID_SALON_PUISSANCE_4 = 1407650674384044033 # Remplacer par l'ID du salon Puissance 4

# Dictionnaire pour stocker les duels en cours.
duels = {}

# Dictionnaire de mappage pour retrouver un duel rapidement par l'ID d'un joueur
duel_by_player = {}

# Emojis pour la grille de Puissance 4
EMOJIS_PUISSANCE_4 = {
    "R": "🔴",
    "J": "🟡",
    " ": "⚫"
}

# Dimensions de la grille
ROWS = 6
COLUMNS = 7

# Commission du croupier
COMMISSION = 0.05

# Connexion à la base de données
conn = sqlite3.connect("connect_four_stats.db")
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS parties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    joueur1_id INTEGER NOT NULL,
    joueur2_id INTEGER NOT NULL,
    montant INTEGER NOT NULL,
    gagnant_id INTEGER,
    est_nul BOOLEAN NOT NULL,
    date TIMESTAMP NOT NULL
)
""")
conn.commit()

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

# --- Logique du jeu de Puissance 4 ---
def check_win(board, player):
    # Vérification horizontale
    for r in range(ROWS):
        for c in range(COLUMNS - 3):
            if board[r][c] == board[r][c+1] == board[r][c+2] == board[r][c+3] == player:
                return True

    # Vérification verticale
    for c in range(COLUMNS):
        for r in range(ROWS - 3):
            if board[r][c] == board[r+1][c] == board[r+2][c] == board[r+3][c] == player:
                return True

    # Vérification diagonale (vers la droite)
    for c in range(COLUMNS - 3):
        for r in range(ROWS - 3):
            if board[r][c] == board[r+1][c+1] == board[r+2][c+2] == board[r+3][c+3] == player:
                return True

    # Vérification diagonale (vers la gauche)
    for c in range(COLUMNS - 3):
        for r in range(3, ROWS):
            if board[r][c] == board[r-1][c+1] == board[r-2][c+2] == board[r-3][c+3] == player:
                return True
    return False

def check_draw(board):
    for r in range(ROWS):
        for c in range(COLUMNS):
            if board[r][c] == " ":
                return False
    return True

def create_board_display(board):
    board_display = ""
    # En-tête des numéros de colonnes
    board_display += "1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣\n"
    for r in range(ROWS):
        for c in range(COLUMNS):
            board_display += EMOJIS_PUISSANCE_4[board[r][c]]
        board_display += "\n"
    return board_display

def create_board_embed(board, title, description, color, turn=None):
    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )
    embed.add_field(name="Grille de jeu", value=create_board_display(board), inline=False)
    if turn:
        embed.add_field(name="Tour de", value=f"{turn.mention}", inline=False)
    return embed

def find_duel_by_user(user_id):
    """Recherche un duel en cours par l'ID d'un utilisateur."""
    if user_id in duel_by_player:
        return duel_by_player[user_id]
    return None, None

def clean_up_duel(joueur1_id, joueur2_id):
    """S'assure de bien supprimer le duel et ses références."""
    duel_key = tuple(sorted((joueur1_id, joueur2_id)))
    if duel_key in duels:
        del duels[duel_key]
    
    if joueur1_id in duel_by_player:
        del duel_by_player[joueur1_id]
    if joueur2_id in duel_by_player:
        del duel_by_player[joueur2_id]


# --- Vues Discord ---
class ConnectFourView(discord.ui.View):
    def __init__(self, duel_data):
        super().__init__(timeout=None)
        self.duel_data = duel_data
        self.board = [[" " for _ in range(COLUMNS)] for _ in range(ROWS)]
        self.joueur1 = duel_data["joueur1"]
        self.joueur2 = duel_data["joueur2"]
        
        self.joueur_actif = random.choice([self.joueur1, self.joueur2])
        self.symboles = {
            self.joueur1.id: "R",
            self.joueur2.id: "J"
        }
        
        self.create_buttons()

    def create_buttons(self):
        self.clear_items()
        for i in range(COLUMNS):
            # Utilisez une condition pour répartir les boutons sur deux lignes
            if i < 5:
                row_number = 0
            else:
                row_number = 1
                
            button = discord.ui.Button(
                label=f"{i+1}",
                style=discord.ButtonStyle.secondary,
                custom_id=f"col_{i}",
                disabled=False,
                row=row_number
            )
            button.callback = self.on_button_click
            self.add_item(button)

    async def on_button_click(self, interaction: discord.Interaction):
        if interaction.user.id != self.joueur_actif.id:
            await interaction.response.send_message("❌ Ce n'est pas ton tour !", ephemeral=True)
            return

        column_index = int(interaction.data["custom_id"].split("_")[1])
        symbole = self.symboles[self.joueur_actif.id]

        # Trouve la première ligne libre dans la colonne
        row_index = -1
        for r in range(ROWS - 1, -1, -1):
            if self.board[r][column_index] == " ":
                row_index = r
                break
        
        if row_index == -1:
            await interaction.response.send_message("❌ Cette colonne est pleine !", ephemeral=True)
            return

        self.board[row_index][column_index] = symbole

        if check_win(self.board, symbole):
            await self.end_game(interaction, self.joueur_actif, is_draw=False)
            return

        if check_draw(self.board):
            await self.end_game(interaction, None, is_draw=True)
            return

        # Passe le tour au joueur suivant
        self.joueur_actif = self.joueur2 if self.joueur_actif.id == self.joueur1.id else self.joueur1
        
        embed = create_board_embed(
            self.board,
            f"⚔️ Duel entre {self.joueur1.display_name} (🔴) et {self.joueur2.display_name} (🟡)",
            "Le jeu est en cours. Fais ton coup !",
            discord.Color.blue(),
            turn=self.joueur_actif
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def end_game(self, interaction: discord.Interaction, winner, is_draw):
        if is_draw:
            title = "🤝 Match nul !"
            description = f"La partie entre {self.joueur1.mention} et {self.joueur2.mention} se termine par un match nul."
            color = discord.Color.greyple()
            gagnant_id = None
        else:
            montant = self.duel_data["montant"]
            gain_net = int(montant * 2 * (1 - COMMISSION))
            # Déterminer le perdant
            loser = self.joueur1 if winner.id != self.joueur1.id else self.joueur2

            title = f"🎉 Victoire de {winner.display_name} !"
            description = (
                f"**{winner.mention}** A battu **{loser.mention}** \n"
                f"--------------------\n"
                f"**{winner.mention}** \n"
                f"**Remporte** **{gain_net:,}** kamas \n (après 5% de commission).\n\n"
                "Félicitations !"
            ).replace(",", " ")
            color = discord.Color.green()
            gagnant_id = winner.id

        
        embed = create_board_embed(self.board, title, description, color)
        # Désactive tous les boutons une fois la partie terminée
        for button in self.children:
            button.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=self)

        # Enregistrement dans la base de données
        now = datetime.utcnow()
        try:
            c.execute(
                "INSERT INTO parties (joueur1_id, joueur2_id, montant, gagnant_id, est_nul, date) VALUES (?, ?, ?, ?, ?, ?)",
                (self.joueur1.id, self.joueur2.id, self.duel_data["montant"], gagnant_id, is_draw, now)
            )
            conn.commit()
        except Exception as e:
            print("❌ Erreur lors de l'insertion dans la base de données:", e)

        # Suppression de l'entrée du duel du dictionnaire
        clean_up_duel(self.joueur1.id, self.joueur2.id)

class RejoindreView(discord.ui.View):
    def __init__(self, message_id, joueur1, montant):
        super().__init__(timeout=None)
        self.message_id_initial = message_id
        self.joueur1 = joueur1
        self.montant = montant
        self.joueur2 = None
        self.croupier = None
        self.duel_data = {
            "joueur1": self.joueur1,
            "montant": self.montant,
            "joueur2": self.joueur2,
            "croupier": self.croupier,
            "message_id_initial": self.message_id_initial
        }

    @discord.ui.button(label="🎯 Rejoindre le duel", style=discord.ButtonStyle.green, custom_id="rejoindre_duel")
    async def rejoindre(self, interaction: discord.Interaction, button: discord.ui.Button):
        joueur2 = interaction.user
        
        if joueur2.id == self.joueur1.id:
            await interaction.response.send_message("❌ Tu ne peux pas rejoindre ton propre duel.", ephemeral=True)
            return
        
        # Vérification si le joueur est déjà dans un duel
        _, existing_duel = find_duel_by_user(joueur2.id)
        if existing_duel:
            await interaction.response.send_message("❌ Tu participes déjà à un autre duel.", ephemeral=True)
            return

        self.joueur2 = joueur2
        self.duel_data["joueur2"] = joueur2
        
        self.children[0].disabled = True
        
        self.add_item(discord.ui.Button(label="🎲 Rejoindre en tant que Croupier", style=discord.ButtonStyle.secondary, custom_id="rejoindre_croupier"))
        self.children[-1].callback = self.rejoindre_croupier

        embed = interaction.message.embeds[0]
        embed.title = f"⚔️ Duel entre {self.joueur1.display_name} et {self.joueur2.display_name}"
        embed.set_field_at(1, name="👤 Joueur 2", value=f"{self.joueur2.mention}", inline=True)
        embed.set_field_at(2, name="Status", value="🕓 Un croupier est attendu pour lancer le duel.", inline=False)
        embed.set_footer(text="Cliquez sur le bouton pour rejoindre en tant que croupier.")
        
        role_croupier = interaction.guild.get_role(ID_CROUPIER)
        contenu_ping = f"{role_croupier.mention} — Un nouveau duel est prêt ! Un croupier est attendu." if role_croupier else ""
        
        await interaction.response.edit_message(
            content=contenu_ping,
            embed=embed,
            view=self,
            allowed_mentions=discord.AllowedMentions(roles=True)
        )
        
        # Mise à jour de l'entrée dans les dictionnaires pour le joueur 2
        duel_key = tuple(sorted((self.joueur1.id, self.joueur2.id)))
        duels[duel_key] = self.duel_data
        duel_by_player[self.joueur2.id] = (duel_key, self.duel_data)
        
        # Correction pour l'entrée du joueur 1, qui peut avoir été ajoutée avec un placeholder
        old_duel_key = tuple(sorted((self.joueur1.id, 0)))
        if old_duel_key in duels:
            del duels[old_duel_key]
        
        duel_by_player[self.joueur1.id] = (duel_key, self.duel_data)

    async def rejoindre_croupier(self, interaction: discord.Interaction):
        role_croupier = interaction.guild.get_role(ID_CROUPIER)
        if not role_croupier or role_croupier not in interaction.user.roles:
            await interaction.response.send_message("❌ Tu n'as pas le rôle de `croupier` pour rejoindre ce duel.", ephemeral=True)
            return

        if self.croupier:
            await interaction.response.send_message("❌ Un croupier a déjà rejoint le duel.", ephemeral=True)
            return
            
        self.croupier = interaction.user
        self.duel_data["croupier"] = self.croupier
        
        embed = interaction.message.embeds[0]
        embed.set_field_at(2, name="Status", value=f"✅ Prêt à jouer ! Croupier : {self.croupier.mention}", inline=False)
        embed.set_footer(text="Le croupier peut lancer la partie.")
        
        self.children[-1].disabled = True
        lancer_button = discord.ui.Button(label="🎮 Lancer la partie", style=discord.ButtonStyle.success, custom_id="lancer_partie", row=1)
        lancer_button.callback = self.lancer_partie
        self.add_item(lancer_button)
        
        await interaction.response.edit_message(content="", embed=embed, view=self)

    async def lancer_partie(self, interaction: discord.Interaction):
        if interaction.user.id != self.croupier.id:
            await interaction.response.send_message("❌ Seul le croupier peut lancer la partie.", ephemeral=True)
            return

        if not self.joueur2:
            await interaction.response.send_message("❌ Le duel n'est pas prêt. Il faut deux joueurs.", ephemeral=True)
            return

        await interaction.response.defer()

        # Supprimer le message initial
        try:
            await interaction.message.delete()
        except discord.NotFound:
            pass

        # Créer le nouveau message pour le jeu de Puissance 4
        connect_four_view = ConnectFourView(self.duel_data)
        embed = create_board_embed(
            connect_four_view.board,
            f"⚔️ Duel entre {self.joueur1.display_name} (🔴) et {self.joueur2.display_name} (🟡)",
            f"Le joueur qui commence est {connect_four_view.joueur_actif.mention}.",
            discord.Color.blue(),
            turn=connect_four_view.joueur_actif
        )

        await interaction.channel.send(embed=embed, view=connect_four_view)


class StatsView(discord.ui.View):
    def __init__(self, ctx, entries, page=0):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.entries = entries
        self.page = page
        self.entries_per_page = 10
        self.max_page = (len(entries) - 1) // self.entries_per_page
        self.update_buttons()

    def update_buttons(self):
        self.first_page.disabled = self.page == 0
        self.prev_page.disabled = self.page == 0
        self.next_page.disabled = self.page == self.max_page
        self.last_page.disabled = self.page == self.max_page
        self.stop_button.disabled = False
        
    def get_embed(self):
        embed = discord.Embed(title="📊 Statistiques Puissance 4", color=discord.Color.gold())
        start = self.page * self.entries_per_page
        end = start + self.entries_per_page
        slice_entries = self.entries[start:end]

        if not slice_entries:
            embed.description = "Aucune donnée à afficher."
            return embed

        description = ""
        for i, (user_id, kamas_mises, kamas_gagnes, victoires, nuls, defaites, total_parties) in enumerate(slice_entries):
            rank = self.page * self.entries_per_page + i + 1
            winrate = (victoires / total_parties * 100) if total_parties > 0 else 0.0
            description += (
                f"**#{rank}** <@{user_id}>\n"
                f"💰 **Misés** : `{kamas_mises:,.0f}` | "
                f"🏆 **Gagnés** : `{kamas_gagnes:,.0f}`\n"
                f"**Victoires** : `{victoires}` | **Nuls**: `{nuls}` | **Défaites**: `{defaites}`\n"
                f"**🎯 Winrate** : `{winrate:.1f}%` (**{victoires}**/**{total_parties}**)\n"
            )
            if i < len(slice_entries) - 1:
                description += "─" * 20 + "\n"

        embed.description = description.replace(",", " ")
        embed.set_footer(text=f"Page {self.page + 1}/{self.max_page + 1}")
        return embed

    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.secondary)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = 0
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_page:
            self.page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = self.max_page
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, custom_id="stop_stats")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content="Fermeture des statistiques.", embed=None, view=None)


# --- Commandes du bot ---
@bot.tree.command(name="sleeping", description="Lancer un duel de Puissance 4 avec un montant.")
@app_commands.describe(montant="Montant misé en kamas")
async def sleeping(interaction: discord.Interaction, montant: int):
    if interaction.channel.id != ID_SALON_PUISSANCE_4:
        await interaction.response.send_message("❌ Cette commande ne peut être utilisée que dans le salon de Puissance 4.", ephemeral=True)
        return
    
    if montant <= 0:
        await interaction.response.send_message("❌ Le montant doit être supérieur à 0.", ephemeral=True)
        return

    _, existing_duel = find_duel_by_user(interaction.user.id)
    if existing_duel:
        await interaction.response.send_message(
            "❌ Tu participes déjà à un autre duel. Termine-le ou utilise `/quit` pour l'annuler.",
            ephemeral=True
        )
        return
            
    embed = discord.Embed(
        title="⚔️ Nouveau Duel Puissance 4 en attente de joueur",
        description=f"{interaction.user.mention} a misé **{f'{montant:,}'.replace(',', ' ')}** kamas pour un duel.",
        color=discord.Color.orange()
    )
    embed.add_field(name="👤 Joueur 1", value=f"{interaction.user.mention}", inline=True)
    embed.add_field(name="👤 Joueur 2", value="🕓 En attente...", inline=True)
    embed.add_field(name="Status", value="🕓 En attente d'un second joueur.", inline=False)
    embed.set_footer(text="Cliquez sur le bouton pour rejoindre le duel.")

    view = RejoindreView(message_id=None, joueur1=interaction.user, montant=montant)
    
    role_membre = interaction.guild.get_role(ID_MEMBRE)
    contenu_ping = f"{role_membre.mention} — Un nouveau duel est prêt ! Un joueur est attendu." if role_membre else ""
    
    await interaction.response.send_message(content=contenu_ping, embed=embed, view=view, allowed_mentions=discord.AllowedMentions(roles=True))
    
    message = await interaction.original_response()
    
    view.message_id_initial = message.id
    
    duel_key = tuple(sorted((interaction.user.id, 0))) 
    view.duel_data["message_id_initial"] = message.id 
    
    duels[duel_key] = view.duel_data
    duel_by_player[interaction.user.id] = (duel_key, view.duel_data)
    

@bot.tree.command(name="quit", description="Annule le duel en cours que tu as lancé ou que tu as rejoint.")
async def quit_duel(interaction: discord.Interaction):
    duel_key, duel_data = find_duel_by_user(interaction.user.id)
    
    if duel_key is None:
        await interaction.response.send_message(
            "❌ Tu n'as aucun duel en attente à annuler ou à quitter.", ephemeral=True)
        return
    
    joueur1 = duel_data["joueur1"]
    joueur2 = duel_data["joueur2"]
    montant = duel_data["montant"]

    try:
        message_initial = await interaction.channel.fetch_message(duel_data["message_id_initial"])
    except discord.NotFound:
        await interaction.response.send_message("❌ Le message du duel initial n'a pas été trouvé. Le duel a été supprimé.", ephemeral=True)
        clean_up_duel(joueur1.id, joueur2.id if joueur2 else 0)
        return

    if interaction.user.id == joueur1.id:
        embed_initial = message_initial.embeds[0]
        embed_initial.title = "❌ Duel annulé"
        embed_initial.description = f"Le duel de **{joueur1.display_name}** a été annulé."
        embed_initial.color = discord.Color.red()
        await message_initial.edit(embed=embed_initial, view=None, content="")
        await interaction.response.send_message("✅ Ton duel a bien été annulé.", ephemeral=True)

        clean_up_duel(joueur1.id, joueur2.id if joueur2 else 0)

    elif joueur2 and interaction.user.id == joueur2.id:
        clean_up_duel(joueur1.id, joueur2.id)

        new_view = RejoindreView(message_id=message_initial.id, joueur1=joueur1, montant=montant)
        
        new_embed = discord.Embed(
            title="⚔️ Nouveau Duel Puissance 4 en attente de joueur",
            description=f"{joueur1.mention} a misé **{f'{montant:,}'.replace(',', ' ')}** kamas pour un duel.",
            color=discord.Color.orange()
        )
        new_embed.add_field(name="👤 Joueur 1", value=f"{joueur1.mention}", inline=True)
        new_embed.add_field(name="👤 Joueur 2", value="🕓 En attente...", inline=True)
        new_embed.add_field(name="Status", value="🕓 En attente d'un second joueur.", inline=False)
        new_embed.set_footer(text="Cliquez sur le bouton pour rejoindre le duel.")

        role_membre = interaction.guild.get_role(ID_MEMBRE)
        contenu_ping = f"{role_membre.mention} — Un nouveau duel est prêt ! Un joueur est attendu." if role_membre else ""
        
        await message_initial.edit(content=contenu_ping, embed=new_embed, view=new_view, allowed_mentions=discord.AllowedMentions(roles=True))
        await interaction.response.send_message("✅ Tu as quitté le duel. Le créateur attend maintenant un autre joueur.", ephemeral=True)

        duel_key_new = tuple(sorted((joueur1.id, 0)))
        new_duel_data = {"joueur1": joueur1, "montant": montant, "joueur2": None, "croupier": None, "message_id_initial": message_initial.id}
        duels[duel_key_new] = new_duel_data
        duel_by_player[joueur1.id] = (duel_key_new, new_duel_data)
    else:
        await interaction.response.send_message(
            "❌ Impossible d'annuler ou de quitter ce duel.", ephemeral=True)


@bot.tree.command(name="statsall", description="Affiche les stats de Puissance 4 à vie.")
async def statsall(interaction: discord.Interaction):
    if interaction.channel.id != ID_SALON_PUISSANCE_4:
        await interaction.response.send_message("❌ Cette commande ne peut être utilisée que dans le salon de Puissance 4.", ephemeral=True)
        return

    c.execute("""
    SELECT joueur_id,
           SUM(montant) as kamas_mises,
           SUM(CASE WHEN gagnant_id = joueur_id THEN montant * 2 * 0.95 ELSE 0 END) as kamas_gagnes,
           SUM(CASE WHEN gagnant_id = joueur_id THEN 1 ELSE 0 END) as victoires,
           SUM(CASE WHEN est_nul = 1 THEN 1 ELSE 0 END) as nuls,
           SUM(CASE WHEN gagnant_id != joueur_id AND est_nul = 0 THEN 1 ELSE 0 END) as defaites,
           COUNT(*) as total_parties
    FROM (
        SELECT joueur1_id as joueur_id, montant, gagnant_id, est_nul FROM parties
        UNION ALL
        SELECT joueur2_id as joueur_id, montant, gagnant_id, est_nul FROM parties
    )
    GROUP BY joueur_id
    ORDER BY kamas_gagnes DESC
    """)
    data = c.fetchall()

    stats = []
    for user_id, kamas_mises, kamas_gagnes, victoires, nuls, defaites, total_parties in data:
        stats.append((user_id, kamas_mises, kamas_gagnes, victoires, nuls, defaites, total_parties))

    if not stats:
        await interaction.response.send_message("Aucune donnée statistique disponible.", ephemeral=True)
        return

    view = StatsView(interaction, stats)
    await interaction.response.send_message(embed=view.get_embed(), view=view, ephemeral=False)

@bot.tree.command(name="mystats", description="Affiche tes statistiques de Puissance 4 personnelles.")
async def mystats(interaction: discord.Interaction):
    user_id = interaction.user.id

    c.execute("""
    SELECT joueur_id,
           SUM(montant) as kamas_mises,
           SUM(CASE WHEN gagnant_id = joueur_id THEN montant * 2 * 0.95 ELSE 0 END) as kamas_gagnes,
           SUM(CASE WHEN est_nul = 1 THEN 1 ELSE 0 END) as nuls,
           SUM(CASE WHEN gagnant_id != joueur_id AND est_nul = 0 THEN 1 ELSE 0 END) as defaites,
           COUNT(*) as total_parties
    FROM (
        SELECT joueur1_id as joueur_id, montant, gagnant_id, est_nul FROM parties
        UNION ALL
        SELECT joueur2_id as joueur_id, montant, gagnant_id, est_nul FROM parties
    )
    WHERE joueur_id = ?
    GROUP BY joueur_id
    """, (user_id,))
    
    stats_data = c.fetchone()

    if not stats_data:
        embed = discord.Embed(
            title="📊 Tes Statistiques Puissance 4",
            description="❌ Tu n'as pas encore participé à un duel. Joue ton premier duel pour voir tes stats !",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    _, kamas_mises, kamas_gagnes, nuls, defaites, total_parties = stats_data
    victoires = total_parties - nuls - defaites
    winrate = (victoires / total_parties * 100) if total_parties > 0 else 0.0

    embed = discord.Embed(
        title=f"📊 Statistiques de {interaction.user.display_name}",
        description="Voici un résumé de tes performances au Puissance 4.",
        color=discord.Color.gold()
    )

    embed.add_field(name="Total gagnés", value=f"**{kamas_gagnes:,.0f}**", inline=True)
    embed.add_field(name=" ", value="─" * 3, inline=False)
    embed.add_field(name="Total misés", value=f"**{kamas_mises:,.0f}**", inline=True)
    embed.add_field(name=" ", value="─" * 20, inline=False)
    embed.add_field(name="Duels joués", value=f"**{total_parties}**", inline=False)
    embed.add_field(name=" ", value="─" * 3, inline=False)
    embed.add_field(name="Victoires", value=f"**{victoires}**", inline=True)
    embed.add_field(name=" ", value="─" * 3, inline=False)
    embed.add_field(name="Nuls", value=f"**{nuls}**", inline=True)
    embed.add_field(name=" ", value="─" * 3, inline=False)
    embed.add_field(name="Défaites", value=f"**{defaites}**", inline=True)
    embed.add_field(name=" ", value="─" * 3, inline=False)
    embed.add_field(name="Taux de victoire", value=f"**{winrate:.1f}%**", inline=False)

    embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
    embed.set_footer(text="Bonne chance pour tes prochains duels !")

    await interaction.response.send_message(embed=embed, ephemeral=True)


# --- Démarrage du bot ---
@bot.event
async def on_ready():
    print(f"{bot.user} est prêt !")
    try:
        await bot.tree.sync()
        print("✅ Commandes synchronisées.")
    except Exception as e:
        print(f"Erreur : {e}")

keep_alive()
bot.run(token)
