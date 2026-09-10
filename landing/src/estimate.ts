export type Assumptions = {
  people: number
  salary: number
  overhead: number
  routineShare: number
  monthlyMinutes: number
  exchangeRate: number
}

export const defaultAssumptions: Assumptions = {
  people: 6,
  salary: 2500,
  overhead: 70,
  routineShare: 60,
  monthlyMinutes: 8000,
  exchangeRate: 5.07,
}

export const costPerMinuteUsd = 0.16

export const currency = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
})

export function calculateEstimate(assumptions: Assumptions) {
  const { people, salary, overhead, routineShare, monthlyMinutes, exchangeRate } = assumptions
  const monthlyTeamCost = people * salary * (1 + overhead / 100)
  const routineCost = monthlyTeamCost * (routineShare / 100)
  const monthlyAiCost = monthlyMinutes * costPerMinuteUsd * exchangeRate
  // Classify the scenario at cent precision, without floating-point residue.
  const monthlyDifference = Math.round((routineCost - monthlyAiCost) * 100) / 100 || 0
  const monthlySavings = Math.max(0, monthlyDifference)

  return {
    monthlyTeamCost,
    routineCost,
    monthlyAiCost,
    monthlyDifference,
    monthlySavings,
    annualSavings: monthlySavings * 12,
    savingsPercentage: routineCost > 0 ? (monthlySavings / routineCost) * 100 : 0,
  }
}
