# utils/graphics.py
# ESTE ARCHIVO PERMANECE IGUAL QUE EN LA VERSIÓN DE DETA
# (El que te proporcioné en el Mensaje 3 de X de la tanda anterior, que usa Matplotlib)

import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
import io
import logging

logger = logging.getLogger(__name__)

COLORS_DISCIPLINE = ['#66BB6A', '#EF5350'] 
COLORS_FINANCE = ['#42A5F5', '#FFA726', '#FFEE58', '#EF5350', '#AB47BC'] 
COLORS_WELLBEING = ['#26A69A', '#FF7043', '#78909C'] 

def generate_pie_chart(labels: list, sizes: list, title: str, colors: list = None) -> io.BytesIO:
    # ... (código idéntico al proporcionado anteriormente para Matplotlib) ...
    # Asegúrate de que plt.close(fig) esté presente al final o en caso de error.
    if not labels or not sizes or len(labels) != len(sizes):
        logger.error("Datos inválidos para generar gráfica de pastel: etiquetas o tamaños vacíos/diferentes longitudes.")
        return None
    
    valid_labels = [label for i, label in enumerate(labels) if sizes[i] > 0]
    valid_sizes = [size for size in sizes if size > 0]
    
    if not valid_labels: 
        logger.info(f"No hay datos para graficar para '{title}'. Todos los valores son cero.")
        return None

    if colors and len(colors) < len(valid_labels):
        effective_colors = (colors * (len(valid_labels) // len(colors) + 1))[:len(valid_labels)]
    elif colors:
        effective_colors = colors[:len(valid_labels)]
    else:
        effective_colors = None 

    fig = None # Inicializar fig por si hay error antes de su asignación
    try:
        fig, ax = plt.subplots(figsize=(7, 5)) 
        
        wedges, texts, autotexts = ax.pie(
            valid_sizes,
            labels=None, 
            autopct='%1.1f%%',
            startangle=90,
            colors=effective_colors,
            pctdistance=0.80
        )

        for autotext in autotexts:
            autotext.set_color('white') 
            autotext.set_fontsize(10)
            autotext.set_fontweight('bold')
        
        ax.axis('equal')  
        
        plt.title(title, fontsize=14, fontweight='bold', pad=20)

        total = sum(valid_sizes)
        legend_labels_with_actual_percent = [
            f'{l} ({s/total*100:.1f}%)' for l, s in zip(valid_labels, valid_sizes) if total > 0 # Evitar división por cero
        ] if total > 0 else valid_labels # Si total es 0, solo mostrar etiquetas

        ax.legend(wedges, legend_labels_with_actual_percent,
                  title="Categorías",
                  loc="center left",
                  bbox_to_anchor=(1, 0, 0.5, 1), 
                  fontsize=9)

        plt.tight_layout(rect=[0, 0, 0.8, 1]) 


        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight') 
        buf.seek(0)
        
        logger.info(f"Gráfica '{title}' generada exitosamente.")
        return buf
        
    except Exception as e:
        logger.error(f"Error generando gráfica de pastel '{title}': {e}")
        return None
    finally:
        if fig: # Asegurarse de que fig fue asignada antes de intentar cerrarla
            plt.close(fig) # Muy importante para liberar memoria


def get_discipline_chart_image(completed_tasks: int, not_done_tasks: int) -> io.BytesIO:
    if completed_tasks == 0 and not_done_tasks == 0:
        return None 
    labels = ['Tareas Completadas', 'Tareas No Hechas']
    sizes = [completed_tasks, not_done_tasks]
    title = "📊 Gráfica de Disciplina Diaria"
    return generate_pie_chart(labels, sizes, title, colors=COLORS_DISCIPLINE)

def get_finance_chart_image(income_extra: float, expenses_variable: float, savings: float, expenses_fixed: float, income_total_bruto: float) -> io.BytesIO:
    if income_total_bruto <= 0:
         logger.info("Ingreso bruto es 0 o negativo, no se puede generar gráfica financiera con porcentajes.")
         return None

    labels = []
    sizes = []
    
    if expenses_fixed > 0:
        labels.append('Gastos Fijos')
        sizes.append(expenses_fixed)
    if expenses_variable > 0:
        labels.append('Gastos Variables')
        sizes.append(expenses_variable)
    if savings > 0:
        labels.append('Ahorros')
        sizes.append(savings)
    
    spent_or_saved = expenses_fixed + expenses_variable + savings
    remaining = income_total_bruto - spent_or_saved

    # Solo añadir 'Disponible' si es positivo y significativo
    if remaining > 0.01 : # Un pequeño umbral para evitar rebanadas diminutas
        labels.append('Disponible/Sobrante')
        sizes.append(remaining)

    if not labels: 
        return None

    title = "💰 Distribución Financiera Mensual"
    return generate_pie_chart(labels, sizes, title, colors=COLORS_FINANCE)


def get_wellbeing_exercise_chart_image(completed_exercises: int, not_done_exercises: int) -> io.BytesIO:
    if completed_exercises == 0 and not_done_exercises == 0:
        return None
    labels = ['Ejercicios Completados', 'Ejercicios No Completados']
    sizes = [completed_exercises, not_done_exercises]
    title = "💪 Gráfica de Ejercicio Diario"
    return generate_pie_chart(labels, sizes, title, colors=COLORS_WELLBEING[:2])


def get_wellbeing_diet_chart_image(diet_fulfilled: int, diet_not_fulfilled: int, extra_meals: int) -> io.BytesIO:
    if diet_fulfilled == 0 and diet_not_fulfilled == 0 and extra_meals == 0:
        return None
    labels = []
    sizes = []
    
    if diet_fulfilled > 0:
        labels.append('Dieta Cumplida')
        sizes.append(diet_fulfilled)
    if diet_not_fulfilled > 0:
        labels.append('Dieta No Cumplida')
        sizes.append(diet_not_fulfilled)
    if extra_meals > 0:
        labels.append('Comidas Extra')
        sizes.append(extra_meals)
        
    if not labels:
        return None

    title = "🍎 Gráfica de Alimentación Diaria"
    return generate_pie_chart(labels, sizes, title, colors=COLORS_WELLBEING)